"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 engine.py                                                       │
│  Module: cyrene_echo.engine                                         │
│  Role: Evaluation ports, artifact adapter, and Exchange adapter.    │
│                                                                     │
│  模块职责：评估端口、本地制品适配器与 Exchange 判官适配器。                │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from cy_artifacts import ArtifactError, ArtifactKind, LocalArtifactProvider
from cy_artifacts import ArtifactRef as PlatformArtifactRef

from cyrene_echo.domain import (
    ArtifactRef,
    EngineEvaluation,
    EvaluationSuite,
    JudgeProfile,
    SampleEvaluation,
    UsageFacts,
)
from cyrene_echo.errors import EchoError, EvaluationEngineFailure
from cyrene_echo.logging import format_cyrene_log


def sha256_file(path: Path) -> str:
    """Return a canonical sha256 digest. | 返回规范 sha256 摘要。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_bytes(data: bytes) -> str:
    """Return a canonical sha256 digest for in-memory bytes. | 返回字节摘要。"""

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _coerce_text(value: Any) -> str | None:
    """Return a text projection of a record field without falsifying None. | 投影文本。"""

    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return str(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


class RunnerProfile(StrEnum):
    """Explicit Echo-owned runner profile. | 运行器配置档。

    A profile is local Product vocabulary; it never names or implies a
    cross-Product capability contract.
    """

    DIRECT_PLUGIN = "DIRECT_PLUGIN"
    PRODUCT_ADAPTER = "PRODUCT_ADAPTER"


class RunnerAcceptance(StrEnum):
    """Acceptance class carried by one runner profile. | 运行器验收分级。"""

    LOCAL_ENDPOINT_VERIFIED = "LOCAL_ENDPOINT_VERIFIED"
    WIRED_NOT_RUN = "WIRED_NOT_RUN"
    # Test doubles only. MOCK is never a selectable runtime binding.
    # 中文:仅用于测试的替身。MOCK 绝不会成为可选的运行时 binding。
    MOCK = "MOCK"


@dataclass(frozen=True)
class RunnerBinding:
    """One declared engine binding with its owner profile. | 运行器绑定。"""

    binding_id: str
    profile: RunnerProfile
    evaluator: str
    acceptance: RunnerAcceptance


RUNNER_BINDINGS: Mapping[str, RunnerBinding] = MappingProxyType(
    {
        "exact-match-plugin": RunnerBinding(
            binding_id="exact-match-plugin",
            profile=RunnerProfile.DIRECT_PLUGIN,
            evaluator="exact_match.v1",
            acceptance=RunnerAcceptance.LOCAL_ENDPOINT_VERIFIED,
        ),
        "exchange-judge": RunnerBinding(
            binding_id="exchange-judge",
            profile=RunnerProfile.PRODUCT_ADAPTER,
            evaluator="llm_judge.v1",
            acceptance=RunnerAcceptance.WIRED_NOT_RUN,
        ),
    }
)


def resolve_runner_binding(binding_id: str) -> RunnerBinding:
    """Resolve a declared runner binding or fail closed. | 解析运行器绑定。"""

    binding = RUNNER_BINDINGS.get(binding_id)
    if binding is None:
        declared = ", ".join(sorted(RUNNER_BINDINGS))
        raise EchoError(
            code="ECHO_RUNNER_BINDING_UNKNOWN",
            title="Unknown engine binding",
            detail=f"Declared Echo runner bindings are: {declared}.",
            status=422,
        )
    return binding


class EvaluationExecutionPort(Protocol):
    """Local application port with no capability authority. | 无能力权威的本地端口。"""

    def evaluate(self, source: Path, suite: EvaluationSuite, report_path: Path) -> EngineEvaluation:
        """Evaluate records and write a staged report. | 评估记录并写入暂存报告。"""


# Complete [0, 1] token only. Reject 2, 1.2, negatives, and prefix "1" from "1.2".
# 只接受完整的 [0,1] 数值, 拒绝越界值及其合法前缀.
_SCORE_PATTERN = re.compile(
    r"score[:\s]*(1(?:\.0*)?|0(?:\.\d+)?|\.\d+)(?![0-9.])",
    re.IGNORECASE,
)


def _parse_judge_score(content: str | None) -> float:
    """Parse a [0,1] score from judge text; never fabricates a value. | 解析判官评分。"""

    if not content:
        return 0.0
    match = _SCORE_PATTERN.search(content)
    if match is None:
        return 0.0
    try:
        value = float(match.group(1))
    except ValueError:
        return 0.0
    if value < 0.0 or value > 1.0:
        return 0.0
    return value


class ExchangeJudgePort:
    """Isolated LLM-judge adapter that calls Exchange (OpenAI-compatible). | Exchange 判官适配器。

    Real judge execution requires a reachable Exchange endpoint and a bearer
    credential. When those are unavailable the port must not be evaluated
    against real production traffic; acceptance is recorded separately as
    ``WIRED_NOT_RUN``. Tests exercise this port against a local stdlib HTTP test
    double, never a real model endpoint.
    """

    def __init__(self, profile: JudgeProfile, *, bearer_token: str) -> None:
        if not bearer_token.strip():
            raise EvaluationEngineFailure("Exchange judge requires a non-empty bearer token.")
        self._profile = profile
        self._bearer_token = bearer_token
        self._judge_identity = f"{profile.judge_model}@{profile.exchange_endpoint_ref}"

    def evaluate(self, source: Path, suite: EvaluationSuite, report_path: Path) -> EngineEvaluation:
        """Invoke the configured judge for each sample through Exchange. | 调用判官。"""

        samples: list[SampleEvaluation] = []
        try:
            with source.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise EvaluationEngineFailure(
                            f"Record {line_number} must be a JSON object."
                        )
                    if suite.expected_field not in record or suite.actual_field not in record:
                        raise EvaluationEngineFailure(
                            f"Record {line_number} is missing an evaluation field."
                        )
                    samples.append(self._judge_one(line_number, record, suite))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EvaluationEngineFailure("The evaluation input is not valid UTF-8 JSONL.") from exc
        if not samples:
            raise EvaluationEngineFailure("The evaluation input contains no records.")
        record_count = len(samples)
        passed_count = sum(1 for sample in samples if sample.passed)
        score = passed_count / record_count
        report_path.write_text(
            json.dumps(
                {
                    "evaluator": suite.evaluator,
                    "judgeIdentity": self._judge_identity,
                    "passedCount": passed_count,
                    "recordCount": record_count,
                    "score": score,
                    "samples": [sample.model_dump(by_alias=True) for sample in samples],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return EngineEvaluation(
            record_count=record_count,
            passed_count=passed_count,
            score=score,
            samples=samples,
        )

    def _judge_one(
        self, sample_index: int, record: dict[str, Any], suite: EvaluationSuite
    ) -> SampleEvaluation:
        """Call Exchange for one record and project honest facts. | 单样本判官调用。"""

        expected = record[suite.expected_field]
        actual = record[suite.actual_field]
        prompt = self._profile.prompt_template
        for token, value in (
            ("{expected}", _coerce_text(expected) or ""),
            ("{actual}", _coerce_text(actual) or ""),
            ("{instruction}", _coerce_text(record.get("instruction")) or ""),
            ("{output}", _coerce_text(record.get("output")) or ""),
        ):
            prompt = prompt.replace(token, value)
        body = json.dumps(
            {
                "model": self._profile.judge_model,
                "messages": [
                    {"role": "system", "content": "You are a strict evaluation judge."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._profile.exchange_endpoint_ref,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._bearer_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise EvaluationEngineFailure(
                f"Exchange judge call failed with HTTP {exc.code}."
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise EvaluationEngineFailure(f"Exchange judge endpoint is unreachable: {exc}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise EvaluationEngineFailure("Exchange judge returned a non-JSON response.") from exc
        content = _extract_message_content(payload)
        usage = _extract_usage(payload)
        score = _parse_judge_score(content)
        return SampleEvaluation(
            sample_index=sample_index,
            input_record=record,
            expected=expected,
            actual=actual,
            raw_output=_coerce_text(record.get("output")) or _coerce_text(actual),
            passed=score >= suite.threshold,
            score=score,
            model_ref=_coerce_text(record.get("model")),
            endpoint_ref=_coerce_text(record.get("endpoint")),
            usage=usage,
            judge_identity=self._judge_identity,
        )


def _extract_message_content(payload: dict[str, Any]) -> str | None:
    """Pull the assistant text from an OpenAI-compatible response. | 提取判官文本。"""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _extract_usage(payload: dict[str, Any]) -> UsageFacts | None:
    """Project Exchange provider usage without estimating missing tokens. | 投影 usage。"""

    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return None
    prompt = _non_bool_int(raw.get("prompt_tokens"))
    completion = _non_bool_int(raw.get("completion_tokens"))
    total = _non_bool_int(raw.get("total_tokens"))
    if prompt is None and completion is None and total is None:
        return None
    try:
        return UsageFacts(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
        )
    except ValueError as exc:
        sys.stderr.write(
            format_cyrene_log(
                level="WARN",
                event_name="echo.engine.invalid_usage_facts",
                message="Failed to instantiate UsageFacts from raw values",
                attributes={
                    "cause": str(exc),
                    "prompt": prompt,
                    "completion": completion,
                    "total": total,
                },
            )
            + "\n"
        )
        return None


def _non_bool_int(value: Any) -> int | None:
    """Return a non-negative int that is not a bool, else None. | 投影真实整数。"""

    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


class ArtifactPlane(Protocol):
    """Local adapter boundary for provider-neutral artifact references. | 本地制品适配端口。"""

    def resolve(self, reference: ArtifactRef) -> Path:
        """Resolve and verify an artifact reference. | 解析并验证制品引用。"""

    def stage_path(self, name: str) -> Path:
        """Return a path for an adapter-owned staged file. | 返回适配器暂存路径。"""

    def publish(self, path: Path) -> ArtifactRef:
        """Publish staged bytes as an artifact reference. | 发布暂存字节。"""

    def publish_bytes(self, data: bytes, *, kind: str) -> ArtifactRef:
        """Publish bytes with a producer-owned kind. | 发布带生产者类别的字节。"""


class EchoArtifactPlane:
    """Platform Artifact SDK adapter for the ArtifactRef wire shape. | Echo 制品适配器。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._provider = LocalArtifactProvider(root)
        self.staging = root / ".staging"
        self.staging.mkdir(parents=True, exist_ok=True)

    def resolve(self, reference: ArtifactRef) -> Path:
        """Resolve and verify canonical content identity. | 解析并验证规范内容标识。"""

        digest_hex = reference.digest.removeprefix("sha256:")
        if reference.uri != f"artifact://sha256/{digest_hex}":
            raise EchoError(
                code="ECHO_ARTIFACT_IDENTITY_INVALID",
                title="Artifact identity invalid",
                detail="The ArtifactRef URI and digest identify different content.",
                status=422,
            )
        try:
            resolved = self._provider.resolve(PlatformArtifactRef.from_dict(reference.model_dump()))
        except ArtifactError as exc:
            raise EchoError(
                code="ECHO_ARTIFACT_UNAVAILABLE",
                title="Artifact unavailable",
                detail="The evaluation input cannot be read.",
                status=422,
            ) from exc
        return Path(resolved.location)

    def stage_path(self, name: str) -> Path:
        """Return an evaluator staging path. | 返回评估器暂存路径。"""

        return self.staging / name

    def publish(self, path: Path) -> ArtifactRef:
        """Publish immutable report bytes. | 发布不可变报告字节。"""

        return self.publish_bytes(path.read_bytes(), kind="report")

    def publish_bytes(self, data: bytes, *, kind: str) -> ArtifactRef:
        """Publish immutable bytes with an explicit artifact kind. | 发布字节制品。"""

        staged = self.stage_path(f"{sha256_bytes(data).removeprefix('sha256:')}.bin")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(data)
        try:
            reference = self._provider.publish(staged, kind=ArtifactKind(kind))
        except ArtifactError as exc:
            raise EchoError(
                code="ECHO_ARTIFACT_UNAVAILABLE",
                title="Artifact unavailable",
                detail="The artifact bytes could not be published.",
                status=422,
            ) from exc
        finally:
            staged.unlink(missing_ok=True)
        return ArtifactRef(**reference.to_dict())

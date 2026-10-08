"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 plugin_evaluation.py                                           │
│  Module: cyrene_echo.plugin_evaluation                             │
│  Role: Product adapter for Plugins-owned evaluation.runner.v1.     │
│                                                                     │
│  模块职责：连接 Plugins 所有的评估能力，不实现评分算法。                   │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cyrene_echo.domain import EngineEvaluation, EvaluationSuite, SampleEvaluation
from cyrene_echo.errors import EvaluationEngineFailure

EVALUATION_RUNNER_CAPABILITY = "evaluation.runner.v1"
EVALUATION_RUNNER_INTERFACE_VERSION = "1"
EVALUATION_RUNNER_CONNECTION_ENV = "CYRENE_EVALUATION_RUNNER_CONNECTION_REF"


@dataclass(frozen=True, slots=True)
class _DirectPayload:
    """Minimal direct payload shape accepted by the shared runtime client.

    中文:共享 runtime client 接受的最小 Direct Plugin payload 结构。
    """

    # 中文:共享运行时客户端接受的最小直传负载形状。

    type_url: str
    value: bytes


class DirectPluginEvaluationPort:
    """Invoke one resolved ``evaluation.runner.v1`` endpoint.

    中文:调用一个已解析的 evaluation.runner.v1 endpoint。
    """

    # 中文:调用一个已解析的 ``evaluation.runner.v1`` 端点。

    def __init__(
        self,
        connection_ref: str,
        *,
        client: Any | None = None,
        deadline_seconds: float = 30.0,
    ) -> None:
        self._client = client or _client_for(connection_ref)
        self._deadline_seconds = deadline_seconds

    def evaluate(
        self,
        source: Path,
        suite: EvaluationSuite,
        report_path: Path,
    ) -> EngineEvaluation:
        """Read Product-owned input and map one typed Plugin measurement.

        中文:读取 Product 自有输入并映射一条类型化 Plugin measurement。
        """
        # 中文:读取 Product 所有的输入并映射一项类型化 Plugin 测量值。

        records = _read_jsonl(source)
        response = self._invoke(
            {
                "records": records,
                "evaluator": suite.evaluator,
                "expected_field": suite.expected_field,
                "actual_field": suite.actual_field,
            }
        )
        measurement = _measurement(response, suite)
        report_path.write_text(
            json.dumps(
                {
                    "evaluator": suite.evaluator,
                    "passedCount": measurement.passed_count,
                    "recordCount": measurement.record_count,
                    "score": measurement.score,
                    "samples": [sample.model_dump(by_alias=True) for sample in measurement.samples],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return measurement

    def _invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        method = "evaluate"
        request_type = f"type.cyrene.io/{EVALUATION_RUNNER_CAPABILITY}.{method}.request"
        response_type = f"type.cyrene.io/{EVALUATION_RUNNER_CAPABILITY}.{method}.response"
        try:
            response = self._client.invoke(
                capability=EVALUATION_RUNNER_CAPABILITY,
                interface_version=EVALUATION_RUNNER_INTERFACE_VERSION,
                method=method,
                request=_DirectPayload(
                    request_type,
                    json.dumps(
                        request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8"),
                ),
                deadline_seconds=self._deadline_seconds,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise EvaluationEngineFailure(f"evaluation.runner.v1 invocation failed: {exc}") from exc
        if response.type_url != response_type:
            raise EvaluationEngineFailure(
                "evaluation.runner.v1 returned type "
                f"{response.type_url!r}; expected {response_type!r}."
            )
        try:
            decoded = json.loads(response.value.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvaluationEngineFailure(
                "evaluation.runner.v1 returned invalid UTF-8 JSON."
            ) from exc
        if not isinstance(decoded, dict):
            raise EvaluationEngineFailure("evaluation.runner.v1 response must be an object.")
        return decoded


class UnavailableEvaluationPort:
    """Fail closed when the required Plugin endpoint is not configured.

    中文:缺少必需的 Plugin endpoint 时应 fail closed。
    """

    # 中文:必需 Plugin 端点未配置时按 fail-closed 处理。

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def evaluate(
        self,
        source: Path,
        suite: EvaluationSuite,
        report_path: Path,
    ) -> EngineEvaluation:
        del source, suite, report_path
        raise EvaluationEngineFailure(f"evaluation.runner.v1 is unavailable: {self._reason}")


def evaluation_port_from_environment() -> DirectPluginEvaluationPort | UnavailableEvaluationPort:
    """Build the default fail-closed Product adapter from an opaque endpoint ref.

    中文:根据不透明 endpoint 引用构建默认的 fail-closed Product adapter。
    """
    # 中文:根据不透明端点引用构建默认的 fail-closed Product 适配器。

    connection_ref = os.environ.get(EVALUATION_RUNNER_CONNECTION_ENV, "").strip()
    if not connection_ref:
        return UnavailableEvaluationPort(
            f"set {EVALUATION_RUNNER_CONNECTION_ENV} to the resolved direct endpoint"
        )
    try:
        return DirectPluginEvaluationPort(connection_ref)
    except EvaluationEngineFailure as exc:
        return UnavailableEvaluationPort(str(exc))


def _client_for(connection_ref: str) -> Any:
    if not isinstance(connection_ref, str) or not connection_ref.strip():
        raise EvaluationEngineFailure("evaluation.runner.v1 connection_ref is empty.")
    try:
        runtime = importlib.import_module("cyrene_plugin_runtime")
    except ImportError as exc:
        raise EvaluationEngineFailure("Plugins direct runtime SDK is not installed.") from exc
    try:
        return runtime.DirectPluginClient.for_local_connection_ref(connection_ref.strip())
    except (TypeError, ValueError) as exc:
        raise EvaluationEngineFailure(
            f"evaluation.runner.v1 connection_ref is invalid: {exc}"
        ) from exc


def _read_jsonl(source: Path) -> list[dict[str, Any]]:
    records = []
    try:
        with source.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise EvaluationEngineFailure(f"Record {line_number} must be a JSON object.")
                records.append({"sample_index": line_number, "record": record})
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationEngineFailure("The evaluation input is not valid UTF-8 JSONL.") from exc
    if not records:
        raise EvaluationEngineFailure("The evaluation input contains no records.")
    return records


def _measurement(response: dict[str, Any], suite: EvaluationSuite) -> EngineEvaluation:
    if response.get("evaluator") != suite.evaluator:
        raise EvaluationEngineFailure("evaluation.runner.v1 returned a mismatched evaluator.")
    values = response.get("samples")
    if not isinstance(values, list):
        raise EvaluationEngineFailure("evaluation.runner.v1 response samples must be an array.")
    if not values:
        raise EvaluationEngineFailure("evaluation.runner.v1 response samples must not be empty.")
    try:
        samples = [SampleEvaluation.model_validate(value) for value in values]
        measurement = EngineEvaluation(
            record_count=_required_integer(response.get("record_count"), "record_count"),
            passed_count=_required_integer(response.get("passed_count"), "passed_count"),
            score=_required_number(response.get("score"), "score"),
            samples=samples,
        )
    except ValidationError as exc:
        raise EvaluationEngineFailure(
            "evaluation.runner.v1 returned an invalid measurement."
        ) from exc
    passed_count = sum(1 for sample in samples if sample.passed)
    expected_score = passed_count / len(samples) if samples else 0.0
    if (
        measurement.record_count != len(samples)
        or measurement.passed_count != passed_count
        or abs(measurement.score - expected_score) > 1e-12
    ):
        raise EvaluationEngineFailure(
            "evaluation.runner.v1 returned inconsistent aggregate measurements."
        )
    return measurement


def _required_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvaluationEngineFailure(f"evaluation.runner.v1 {field} must be an integer.")
    return value


def _required_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvaluationEngineFailure(f"evaluation.runner.v1 {field} must be a number.")
    return float(value)


__all__ = [
    "EVALUATION_RUNNER_CAPABILITY",
    "EVALUATION_RUNNER_CONNECTION_ENV",
    "EVALUATION_RUNNER_INTERFACE_VERSION",
    "DirectPluginEvaluationPort",
    "UnavailableEvaluationPort",
    "evaluation_port_from_environment",
]

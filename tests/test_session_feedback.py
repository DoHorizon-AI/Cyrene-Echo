"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 test_session_feedback.py                                        │
│  Module: tests.test_session_feedback                                 │
│  Role: Session → evaluation → human review → Catalyst handoff path. │
│                                                                     │
│  模块职责：验证会话评估、逐样本结果、人工标注、筛选、反馈集导出与判官适配器。 │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import shutil
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from cyrene_echo import create_app
from cyrene_echo.engine import _parse_judge_score, sha256_file


def _publish_jsonl(client: TestClient, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Publish a JSONL document of session records as a dataset artifact. | 发布会话制品。"""

    payload = ("\n".join(json.dumps(record) for record in records) + "\n").encode("utf-8")
    response = client.post("/api/v1/session-artifacts", content=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _stage_artifact(path: Path, artifact_root: Path) -> dict[str, Any]:
    """Copy a local file into the artifact plane and return its ArtifactRef. | 投入制品。"""

    digest = sha256_file(path)
    digest_hex = digest.removeprefix("sha256:")
    objects = artifact_root / "sha256"
    objects.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, objects / digest_hex)
    return {
        "uri": f"artifact://sha256/{digest_hex}",
        "digest": digest,
        "size_bytes": path.stat().st_size,
        "kind": "dataset",
    }


def _close(app: Any) -> None:
    app.state.echo_store.close()


# ════════════════════════════════════════════════════════════════════
# SECTION: Deterministic session → feedback → Catalyst export path
# ════════════════════════════════════════════════════════════════════
def test_session_to_feedback_export_deterministic(tmp_path: Path) -> None:
    records = [
        {
            "instruction": "2+2?",
            "expected": "4",
            "actual": "4",
            "output": "4",
            "model": "qwen-demo",
            "endpoint": "http://reactor/v1",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
        {
            "instruction": "首都?",
            "expected": "北京",
            "actual": "上海",
            "output": "上海",
            "model": "qwen-demo",
            "endpoint": "http://reactor/v1",
        },
        {
            "instruction": "水分子式?",
            "expected": "H2O",
            "actual": "H2O",
            "output": "H2O",
            "model": "qwen-demo",
            "endpoint": "http://reactor/v1",
        },
    ]
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(client, records)
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "session-exact",
                "evaluator": "exact_match.v1",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.7,
            },
        ).json()
        run = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        ).json()
        assert run["state"] == "SUCCEEDED"
        result = client.get(f"/api/v1/evaluation-results/{run['resultId']}").json()
        gate = client.get(f"/api/v1/gate-decisions/{run['gateId']}").json()
        # Success-but-poor-score: run SUCCEEDED, gate FAIL (2/3 ≈ 0.667 < 0.7).
        assert result["score"] == pytest.approx(2 / 3)
        assert gate["outcome"] == "FAIL"
        # Per-sample results preserve evaluated model/endpoint/input version/usage.
        samples = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples").json()
        assert len(samples) == 3
        assert {s["sampleIndex"] for s in samples} == {1, 2, 3}
        first = next(s for s in samples if s["sampleIndex"] == 1)
        assert first["passed"] is True
        assert first["modelRef"] == "qwen-demo"
        assert first["endpointRef"] == "http://reactor/v1"
        assert first["inputDigest"] == run["inputArtifact"]["digest"]
        assert first["usage"]["promptTokens"] == 5
        second = next(s for s in samples if s["sampleIndex"] == 2)
        assert second["passed"] is False
        # Model did not provide Usage for sample 2 → honest None, never estimated.
        assert second["usage"] is None
        assert second["judgeIdentity"] is None

        # Human correction on the low-score sample 2.
        annotation = client.post(
            f"/api/v1/evaluation-runs/{run['id']}/annotations",
            json={
                "sampleIndex": 2,
                "reviewer": "qa",
                "manualScore": 0.0,
                "correctedOutput": "北京",
                "preference": "prefer_corrected",
                "note": "wrong capital",
            },
        ).json()
        assert annotation["sampleIndex"] == 2
        annotations = client.get(f"/api/v1/evaluation-runs/{run['id']}/annotations").json()
        assert len(annotations) == 1
        # Filtering: only-failed returns sample 2; only-annotated returns sample 2.
        failed = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples?only_passed=false").json()
        assert [s["sampleIndex"] for s in failed] == [2]
        annotated = client.get(
            f"/api/v1/evaluation-runs/{run['id']}/samples?only_annotated=true"
        ).json()
        assert [s["sampleIndex"] for s in annotated] == [2]

        # FeedbackSet built ONLY from explicitly selected samples (sample 2).
        feedback = client.post(
            "/api/v1/feedback-sets",
            json={
                "name": "demo-feedback",
                "runId": run["id"],
                "sampleIndexes": [2],
                "annotationIds": [annotation["id"]],
            },
        ).json()
        assert feedback["sampleIndexes"] == [2]
        assert feedback["handoffStatus"] == "PREPARED"
        exported = client.post(f"/api/v1/feedback-sets/{feedback['id']}/export").json()
        assert exported["handoffStatus"] == "PREPARED"
        assert exported["candidateCount"] == 1
        export_artifact = exported["feedbackSet"]["exportArtifact"]
        assert export_artifact["kind"] == "dataset"
        assert export_artifact["digest"].startswith("sha256:")
        # Download the Catalyst-compatible JSONL and verify provenance.
        download = client.get(f"/api/v1/feedback-sets/{feedback['id']}/export")
        assert download.headers["content-type"] == "application/jsonl"
        rows = [json.loads(line) for line in download.text.splitlines() if line.strip()]
        assert len(rows) == 1
        row = rows[0]
        assert row["instruction"] == "首都?"
        assert row["output"] == "北京"
        assert row["sourceKind"] == "preference"
        assert row["rejectedOutput"] == "上海"
        assert row["annotatedBy"] == "qa"
        assert row["sourceRunId"] == run["id"]
        assert row["sourceSampleIndex"] == 2
    _close(app)


# ════════════════════════════════════════════════════════════════════
# SECTION: Held-out evaluation samples are never auto-exported as training data
# ════════════════════════════════════════════════════════════════════
def test_unselected_samples_are_not_exported_as_training_data(tmp_path: Path) -> None:
    records = [
        {"instruction": f"q{i}", "expected": str(i), "actual": str(i), "output": str(i)}
        for i in range(1, 6)
    ]
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(client, records)
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "heldout",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.5,
            },
        ).json()
        run = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        ).json()
        # Only sample 3 is explicitly selected; 1,2,4,5 are held-out eval samples.
        feedback = client.post(
            "/api/v1/feedback-sets",
            json={
                "name": "single",
                "runId": run["id"],
                "sampleIndexes": [3],
            },
        ).json()
        client.post(f"/api/v1/feedback-sets/{feedback['id']}/export")
        download = client.get(f"/api/v1/feedback-sets/{feedback['id']}/export")
        rows = [json.loads(line) for line in download.text.splitlines() if line.strip()]
        assert [r["sourceSampleIndex"] for r in rows] == [3]
    _close(app)


# ════════════════════════════════════════════════════════════════════
# SECTION: Evaluation failure vs success-low-score vs no-usage vs human-vs-model
# ════════════════════════════════════════════════════════════════════
def test_evaluation_failure_is_distinct_from_poor_score(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    with TestClient(app) as client:
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "broken",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.5,
            },
        ).json()
        broken = tmp_path / "broken.jsonl"
        broken.write_text('{"expected": [}\n', encoding="utf-8")
        artifact = _stage_artifact(broken, tmp_path / "artifacts")
        response = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        )
        assert response.status_code == 422
        problem = response.json()
        assert problem["code"] == "ECHO_EVALUATION_FAILED"
        run = client.get(problem["resourceRef"]).json()
        assert run["state"] == "FAILED"
        assert run["failure"]["code"] == "ECHO_EVALUATION_FAILED"
    _close(app)


def test_human_annotation_is_distinct_from_model_score(tmp_path: Path) -> None:
    records = [{"instruction": "q", "expected": "good", "actual": "bad", "output": "bad"}]
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(client, records)
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "disagree",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 1.0,
            },
        ).json()
        run = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        ).json()
        sample = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples/1").json()
        # Model/deterministic score says FAIL (0.0); human says manual_score 0.9.
        assert sample["passed"] is False
        annotation = client.post(
            f"/api/v1/evaluation-runs/{run['id']}/annotations",
            json={
                "sampleIndex": 1,
                "reviewer": "human",
                "manualScore": 0.9,
                "correctedOutput": "good",
                "preference": "accept",
                "note": "model was wrong",
            },
        ).json()
        assert annotation["manualScore"] == 0.9
        # Both the model score and the human opinion are preserved independently.
        sample_after = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples/1").json()
        assert sample_after["score"] == 0.0
        assert sample_after["passed"] is False
    _close(app)


# ════════════════════════════════════════════════════════════════════
# SECTION: Judge score parser rejects out-of-range tokens
# ════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("SCORE: 0", 0.0),
        ("SCORE: 1", 1.0),
        ("SCORE: 0.0", 0.0),
        ("SCORE: 1.0", 1.0),
        ("SCORE: 0.5", 0.5),
        ("SCORE: .75", 0.75),
        ("SCORE: 1.000", 1.0),
        ("score:0", 0.0),
        ("SCORE: 2", 0.0),
        ("SCORE: 2.0", 0.0),
        ("SCORE: 1.2", 0.0),
        ("SCORE: 1.20", 0.0),
        ("SCORE: 10", 0.0),
        ("SCORE: -1", 0.0),
        ("SCORE: -0.5", 0.0),
        ("SCORE: 1.0001", 0.0),
        (None, 0.0),
        ("", 0.0),
        ("no score here", 0.0),
    ],
)
def test_parse_judge_score_zero_to_one_bounds(content: str | None, expected: float) -> None:
    assert _parse_judge_score(content) == expected


def test_parse_judge_score_does_not_accept_illegal_tokens_as_valid_scores() -> None:
    """Out-of-range tokens must not enter as 2, 1.2, or a prefix 1.0. | 越界不得入分。"""

    assert _parse_judge_score("SCORE: 2") == 0.0
    assert _parse_judge_score("SCORE: 1.2") == 0.0
    assert _parse_judge_score("SCORE: 1.2") != 1.0
    assert _parse_judge_score("SCORE: -1") == 0.0
    assert _parse_judge_score("SCORE: -0.5") == 0.0


# ════════════════════════════════════════════════════════════════════
# SECTION: Exchange judge adapter against a local stdlib HTTP test double
# ════════════════════════════════════════════════════════════════════
class _JudgeDoubleHandler(BaseHTTPRequestHandler):
    """A local OpenAI-compatible test double for Exchange; NOT a real judge. | 测试替身。"""

    judge_score = 0.9
    include_usage = True

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/v1/chat/completions":
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            return
        content = f"SCORE: {_JudgeDoubleHandler.judge_score}"
        body: dict[str, Any] = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        }
        if _JudgeDoubleHandler.include_usage:
            body["usage"] = {
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "total_tokens": 14,
            }
        self._json(HTTPStatus.OK, body)

    def _json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def judge_double() -> Any:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _JudgeDoubleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_exchange_judge_adapter_records_usage_and_judge_identity(
    tmp_path: Path, judge_double: Any
) -> None:
    port = judge_double.server_address[1]
    endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
    records = [
        {
            "instruction": "answer",
            "expected": "good",
            "actual": "bad",
            "output": "bad",
            "model": "qwen-demo",
            "endpoint": "http://reactor/v1",
        }
    ]
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        judge_bearer_token="test-double-token",
    )
    with TestClient(app) as client:
        profile = client.post(
            "/api/v1/judge-profiles",
            json={
                "name": "double-judge",
                "judgeModel": "judge-test-model",
                "exchangeEndpointRef": endpoint,
                "promptTemplate": "Judge this: {instruction} expected={expected} actual={actual}",
            },
        ).json()
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "judge-suite",
                "evaluator": "llm_judge.v1",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.8,
                "judgeProfileId": profile["id"],
            },
        ).json()
        artifact = _publish_jsonl(client, records)
        run = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exchange-judge",
            },
        ).json()
        assert run["state"] == "SUCCEEDED"
        sample = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples/1").json()
        assert sample["evaluator"] == "llm_judge.v1"
        assert sample["judgeIdentity"] == f"judge-test-model@{endpoint}"
        assert sample["usage"]["promptTokens"] == 11
        assert sample["usage"]["totalTokens"] == 14
        assert sample["score"] == pytest.approx(0.9)
        assert sample["passed"] is True
    _close(app)


def test_exchange_judge_without_usage_records_none(tmp_path: Path, judge_double: Any) -> None:
    port = judge_double.server_address[1]
    endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
    _JudgeDoubleHandler.include_usage = False
    try:
        records = [
            {
                "instruction": "answer",
                "expected": "good",
                "actual": "bad",
                "output": "bad",
            }
        ]
        app = create_app(
            database_path=tmp_path / "echo.sqlite3",
            artifact_root=tmp_path / "artifacts",
            judge_bearer_token="test-double-token",
        )
        with TestClient(app) as client:
            profile = client.post(
                "/api/v1/judge-profiles",
                json={
                    "name": "no-usage-judge",
                    "judgeModel": "judge-test-model",
                    "exchangeEndpointRef": endpoint,
                    "promptTemplate": "Judge: {actual}",
                },
            ).json()
            suite = client.post(
                "/api/v1/evaluation-suites",
                json={
                    "name": "no-usage",
                    "evaluator": "llm_judge.v1",
                    "expectedField": "expected",
                    "actualField": "actual",
                    "threshold": 0.5,
                    "judgeProfileId": profile["id"],
                },
            ).json()
            artifact = _publish_jsonl(client, records)
            run = client.post(
                "/api/v1/evaluation-runs",
                json={
                    "suiteId": suite["id"],
                    "inputArtifact": artifact,
                    "engineBindingId": "exchange-judge",
                },
            ).json()
            sample = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples/1").json()
            # Model did not provide Usage → honest None, never estimated.
            assert sample["usage"] is None
    finally:
        _JudgeDoubleHandler.include_usage = True


def test_real_judge_without_credential_is_wired_not_run(tmp_path: Path) -> None:
    """Real Exchange judge is WIRED_NOT_RUN without a bearer credential. | 真实判官未运行。"""

    records = [{"instruction": "q", "expected": "a", "actual": "b", "output": "b"}]
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        judge_bearer_token=None,
    )
    with TestClient(app) as client:
        profile = client.post(
            "/api/v1/judge-profiles",
            json={
                "name": "real-judge",
                "judgeModel": "gpt-4o",
                "exchangeEndpointRef": "http://exchange.local/v1/chat/completions",
                "promptTemplate": "Judge: {actual}",
            },
        ).json()
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "real-judge-suite",
                "evaluator": "llm_judge.v1",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.5,
                "judgeProfileId": profile["id"],
            },
        ).json()
        artifact = _publish_jsonl(client, records)
        response = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exchange-judge",
            },
        )
        assert response.status_code == 503
        problem = response.json()
        assert problem["code"] == "ECHO_JUDGE_CREDENTIAL_UNAVAILABLE"
        assert "WIRED_NOT_RUN" in problem["detail"]
        run = client.get(problem["resourceRef"]).json()
        assert run["state"] == "FAILED"
    _close(app)


def test_llm_judge_suite_requires_judge_profile(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        judge_bearer_token="test-double-token",
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "no-profile",
                "evaluator": "llm_judge.v1",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.5,
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "ECHO_SUITE_JUDGE_PROFILE_REQUIRED"
    _close(app)


# ════════════════════════════════════════════════════════════════════
# SECTION: Wire outputs conform to the frozen JSON Schemas
# ════════════════════════════════════════════════════════════════════
def _registry() -> Registry:
    contract_root = Path(__file__).parents[1] / "contracts/product/v1"
    artifact_schema = json.loads(
        (contract_root / "generated/platform/artifact-ref.schema.json").read_text()
    )
    return Registry().with_resource(artifact_schema["$id"], Resource.from_contents(artifact_schema))


def test_sample_record_and_feedback_set_match_frozen_schemas(tmp_path: Path) -> None:
    records = [
        {"instruction": "q1", "expected": "a", "actual": "a", "output": "a", "model": "m"},
        {"instruction": "q2", "expected": "b", "actual": "x", "output": "x", "model": "m"},
    ]
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(client, records)
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "schema-suite",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 1.0,
            },
        ).json()
        run = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        ).json()
        annotation = client.post(
            f"/api/v1/evaluation-runs/{run['id']}/annotations",
            json={
                "sampleIndex": 2,
                "reviewer": "qa",
                "correctedOutput": "b",
                "preference": "prefer_corrected",
            },
        ).json()
        feedback = client.post(
            "/api/v1/feedback-sets",
            json={
                "name": "schema-feedback",
                "runId": run["id"],
                "sampleIndexes": [2],
                "annotationIds": [annotation["id"]],
            },
        ).json()
        client.post(f"/api/v1/feedback-sets/{feedback['id']}/export")
        exported = client.get(f"/api/v1/feedback-sets/{feedback['id']}").json()

        contract_root = Path(__file__).parents[1] / "contracts/product/v1"
        registry = _registry()
        checker = FormatChecker()

        sample = client.get(f"/api/v1/evaluation-runs/{run['id']}/samples/2").json()
        sample_schema = json.loads((contract_root / "sample-record.schema.json").read_text())
        Draft202012Validator(sample_schema, registry=registry, format_checker=checker).validate(
            sample
        )

        annotation_schema = json.loads((contract_root / "human-annotation.schema.json").read_text())
        Draft202012Validator(annotation_schema, registry=registry, format_checker=checker).validate(
            annotation
        )

        feedback_schema = json.loads((contract_root / "feedback-set.schema.json").read_text())
        Draft202012Validator(feedback_schema, registry=registry, format_checker=checker).validate(
            exported
        )

        profile = client.post(
            "/api/v1/judge-profiles",
            json={
                "name": "schema-judge",
                "judgeModel": "judge-x",
                "exchangeEndpointRef": "http://exchange.local/v1/chat/completions",
                "promptTemplate": "Judge: {actual}",
            },
        ).json()
        profile_schema = json.loads((contract_root / "judge-profile.schema.json").read_text())
        Draft202012Validator(profile_schema, registry=registry, format_checker=checker).validate(
            profile
        )
    _close(app)

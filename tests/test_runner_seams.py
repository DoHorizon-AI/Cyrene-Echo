"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 test_runner_seams.py                                            │
│  Module: tests.test_runner_seams                                     │
│  Role: Runner profile bindings and fail-closed product seams.        │
│                                                                     │
│  模块职责：验证运行器绑定分级，以及 Exchange 判官与 Catalyst 交接的 fail-closed。│
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from fastapi.testclient import TestClient

from cyrene_echo import create_app
from cyrene_echo.engine import (
    RUNNER_BINDINGS,
    RunnerAcceptance,
    RunnerProfile,
    resolve_runner_binding,
)
from cyrene_echo.plugin_evaluation import UnavailableEvaluationPort


def _close(app: Any) -> None:
    app.state.echo_store.close()


def _publish_jsonl(client: TestClient, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Publish session records as an immutable dataset artifact. | 发布制品。"""

    payload = ("\n".join(json.dumps(record) for record in records) + "\n").encode("utf-8")
    response = client.post("/api/v1/session-artifacts", content=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _unreachable_url() -> str:
    """Bind then release a local port so nothing can answer. | 确定不可达地址。"""

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _exact_suite(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/evaluation-suites",
        json={
            "name": "seam-exact",
            "evaluator": "exact_match.v1",
            "expectedField": "expected",
            "actualField": "actual",
            "threshold": 0.5,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _judge_suite(client: TestClient, endpoint: str) -> dict[str, Any]:
    profile = client.post(
        "/api/v1/judge-profiles",
        json={
            "name": "seam-judge",
            "judgeModel": "judge-model",
            "exchangeEndpointRef": endpoint,
            "promptTemplate": "Judge: {actual}",
        },
    )
    assert profile.status_code == 201, profile.text
    response = client.post(
        "/api/v1/evaluation-suites",
        json={
            "name": "seam-llm",
            "evaluator": "llm_judge.v1",
            "expectedField": "expected",
            "actualField": "actual",
            "threshold": 0.5,
            "judgeProfileId": profile.json()["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _exported_feedback_set(client: TestClient) -> str:
    """Create one exported FeedbackSet ready for an explicit handoff. | 准备反馈集。"""

    artifact = _publish_jsonl(
        client,
        [{"instruction": "q", "expected": "a", "actual": "b", "output": "b"}],
    )
    suite = _exact_suite(client)
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
            "sampleIndex": 1,
            "reviewer": "reviewer",
            "correctedOutput": "a",
            "manualScore": 1,
        },
    ).json()
    feedback = client.post(
        "/api/v1/feedback-sets",
        json={
            "name": "seam-selection",
            "runId": run["id"],
            "sampleIndexes": [1],
            "annotationIds": [annotation["id"]],
        },
    ).json()
    exported = client.post(f"/api/v1/feedback-sets/{feedback['id']}/export")
    assert exported.status_code == 200, exported.text
    return feedback["id"]


class _HttpStub:
    """Minimal HTTP double used to prove fail-closed and receipt mapping. | 测试替身。"""

    def __init__(self, handler_type: type[BaseHTTPRequestHandler]) -> None:
        self.requests: list[dict[str, Any]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class _RejectingJudge(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        _json_response(self, 500, {"error": "judge unavailable"})

    def log_message(self, format: str, *args: Any) -> None:
        return


class _CatalystDouble(BaseHTTPRequestHandler):
    receipt: ClassVar[dict[str, Any] | None] = None
    requests: ClassVar[list[dict[str, Any]]] = []
    response_status: ClassVar[int] = 201

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append(
            {
                "path": self.path,
                "idempotency_key": self.headers.get("Idempotency-Key"),
                "body": body,
            }
        )
        assert _CatalystDouble.receipt is not None
        _json_response(self, _CatalystDouble.response_status, _CatalystDouble.receipt)

    def log_message(self, format: str, *args: Any) -> None:
        return


# ════════════════════════════════════════════════════════════════════
# SECTION: Runner profile and binding declarations
# ════════════════════════════════════════════════════════════════════
def test_runner_bindings_are_explicit_and_mock_is_not_selectable() -> None:
    """Bindings declare owner profiles and grading; mocks stay test-only. | 绑定分级。"""

    assert set(RUNNER_BINDINGS) == {"exact-match-plugin", "exchange-judge"}
    local = RUNNER_BINDINGS["exact-match-plugin"]
    assert (local.profile, local.evaluator, local.acceptance) == (
        RunnerProfile.DIRECT_PLUGIN,
        "exact_match.v1",
        RunnerAcceptance.LOCAL_ENDPOINT_VERIFIED,
    )
    remote = RUNNER_BINDINGS["exchange-judge"]
    assert (remote.profile, remote.evaluator, remote.acceptance) == (
        RunnerProfile.PRODUCT_ADAPTER,
        "llm_judge.v1",
        RunnerAcceptance.WIRED_NOT_RUN,
    )
    assert RunnerAcceptance.MOCK not in {binding.acceptance for binding in RUNNER_BINDINGS.values()}
    # Binding ids are Echo-local names; no fabricated capability id is selectable.
    assert all(not binding_id.startswith("evaluation.") for binding_id in RUNNER_BINDINGS)
    assert resolve_runner_binding("exchange-judge") is remote


def test_unknown_runner_binding_is_rejected_before_execution(tmp_path: Path) -> None:
    """An undeclared binding fails closed instead of running a default. | 未声明绑定即失败。"""

    app = create_app(database_path=tmp_path / "echo.sqlite3", artifact_root=tmp_path / "artifacts")
    with TestClient(app) as client:
        artifact = _publish_jsonl(
            client, [{"instruction": "q", "expected": "a", "actual": "a", "output": "a"}]
        )
        suite = _exact_suite(client)
        response = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "evaluation.runner.v1",
            },
        )
        assert response.status_code == 422
        problem = response.json()
        assert problem["code"] == "ECHO_RUNNER_BINDING_UNKNOWN"
        assert "exact-match-plugin" in problem["detail"]
    _close(app)


def test_exact_match_binding_fails_closed_without_plugin_endpoint(tmp_path: Path) -> None:
    """A missing evaluation Plugin never falls back to Product-local scoring. | 缺失插件不回退。"""

    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        engine=UnavailableEvaluationPort("connection_ref is not configured"),
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(client, [{"instruction": "q", "expected": "a", "actual": "a"}])
        suite = _exact_suite(client)
        response = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "ECHO_EVALUATION_FAILED"
        assert "evaluation.runner.v1 is unavailable" in response.json()["detail"]
    _close(app)


def test_echo_production_tree_contains_only_the_direct_evaluation_adapter() -> None:
    production = Path(__file__).resolve().parents[1] / "src" / "cyrene_echo"
    engine_source = (production / "engine.py").read_text(encoding="utf-8")
    adapter_source = (production / "plugin_evaluation.py").read_text(encoding="utf-8")

    assert "ExactMatchJsonlPort" not in engine_source
    assert "expected == actual" not in engine_source
    assert "DirectPluginClient" in adapter_source


def test_runner_binding_must_match_suite_evaluator(tmp_path: Path) -> None:
    """A binding declared for another evaluator cannot execute a suite. | 绑定不匹配。"""

    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        judge_bearer_token="token",
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(
            client, [{"instruction": "q", "expected": "a", "actual": "a", "output": "a"}]
        )
        exact_suite = _exact_suite(client)
        judge_suite = _judge_suite(client, "http://127.0.0.1:9/v1/chat/completions")
        mismatch_exact = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": exact_suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exchange-judge",
            },
        )
        mismatch_judge = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": judge_suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exact-match-plugin",
            },
        )
        for response in (mismatch_exact, mismatch_judge):
            assert response.status_code == 422
            assert response.json()["code"] == "ECHO_RUNNER_BINDING_MISMATCH"
    _close(app)


# ════════════════════════════════════════════════════════════════════
# SECTION: Exchange judge fail-closed
# ════════════════════════════════════════════════════════════════════
def test_exchange_judge_unreachable_endpoint_fails_closed(tmp_path: Path) -> None:
    """A configured judge endpoint that is down must not fabricate scores. | 不可达判官。"""

    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        judge_bearer_token="token",
    )
    with TestClient(app) as client:
        artifact = _publish_jsonl(
            client, [{"instruction": "q", "expected": "a", "actual": "b", "output": "b"}]
        )
        suite = _judge_suite(client, _unreachable_url() + "/v1/chat/completions")
        response = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": artifact,
                "engineBindingId": "exchange-judge",
            },
        )
        assert response.status_code == 422
        problem = response.json()
        assert problem["code"] == "ECHO_EVALUATION_FAILED"
        persisted = client.get(problem["resourceRef"]).json()
        assert persisted["state"] == "FAILED"
    _close(app)


def test_exchange_judge_rejection_fails_closed(tmp_path: Path) -> None:
    """An HTTP rejection from the judge is a failed run, never a score. | 判官拒绝。"""

    stub = _HttpStub(_RejectingJudge)
    try:
        app = create_app(
            database_path=tmp_path / "echo.sqlite3",
            artifact_root=tmp_path / "artifacts",
            judge_bearer_token="token",
        )
        with TestClient(app) as client:
            artifact = _publish_jsonl(
                client, [{"instruction": "q", "expected": "a", "actual": "b", "output": "b"}]
            )
            suite = _judge_suite(client, stub.url + "/v1/chat/completions")
            response = client.post(
                "/api/v1/evaluation-runs",
                json={
                    "suiteId": suite["id"],
                    "inputArtifact": artifact,
                    "engineBindingId": "exchange-judge",
                },
            )
            assert response.status_code == 422
            problem = response.json()
            assert problem["code"] == "ECHO_EVALUATION_FAILED"
            assert client.get(problem["resourceRef"]).json()["state"] == "FAILED"
        _close(app)
    finally:
        stub.close()


# ════════════════════════════════════════════════════════════════════
# SECTION: Catalyst feedback handoff fail-closed
# ════════════════════════════════════════════════════════════════════
def test_catalyst_handoff_requires_configured_endpoint(tmp_path: Path) -> None:
    """Without a configured Catalyst URL the handoff fails closed. | 未配置端点。"""

    app = create_app(database_path=tmp_path / "echo.sqlite3", artifact_root=tmp_path / "artifacts")
    with TestClient(app) as client:
        feedback_id = _exported_feedback_set(client)
        response = client.post(
            f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst", json={}
        )
        assert response.status_code == 503
        assert response.json()["code"] == "ECHO_CATALYST_NOT_CONNECTED"
    _close(app)


def test_catalyst_handoff_unreachable_keeps_export_prepared(tmp_path: Path) -> None:
    """An unreachable Catalyst must not mark the export as delivered. | 未投递。"""

    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        catalyst_url=_unreachable_url(),
    )
    with TestClient(app) as client:
        feedback_id = _exported_feedback_set(client)
        response = client.post(
            f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst", json={}
        )
        assert response.status_code == 502
        problem = response.json()
        assert problem["code"] == "ECHO_CATALYST_HANDOFF_FAILED"
        assert problem["retryable"] is True
        assert client.get(f"/api/v1/feedback-sets/{feedback_id}").json()["handoffStatus"] == (
            "PREPARED"
        )
    _close(app)


def test_catalyst_handoff_returns_owner_confirmed_receipt(tmp_path: Path) -> None:
    """A confirmed target acknowledgement maps to one normalized receipt. | 回执映射。"""

    target_id = str(uuid4())
    _CatalystDouble.requests = []
    _CatalystDouble.response_status = 201
    _CatalystDouble.receipt = {
        "status": "DRAFT",
        "targetResource": {
            "uri": f"cyrene://catalyst/preparations/{target_id}",
            "id": target_id,
            "resourceVersion": 1,
        },
        "openIn": f"/api/v1/preparations/{target_id}",
    }
    stub = _HttpStub(_CatalystDouble)
    try:
        app = create_app(
            database_path=tmp_path / "echo.sqlite3",
            artifact_root=tmp_path / "artifacts",
            catalyst_url=stub.url,
        )
        with TestClient(app) as client:
            feedback_id = _exported_feedback_set(client)
            response = client.post(
                f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst", json={}
            )
            assert response.status_code == 200, response.text
            receipt = response.json()
            assert receipt["status"] == "DRAFT"
            assert receipt["targetResource"]["id"] == target_id
            assert receipt["openIn"] == f"{stub.url}/api/v1/preparations/{target_id}"
            persisted = client.get(f"/api/v1/feedback-sets/{feedback_id}").json()
            assert persisted["handoffStatus"] == "HANDLED_OFF"
            assert persisted["resourceVersion"] == 3
            replay = client.post(
                f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst", json={}
            )
            assert replay.json() == receipt
            conflict = client.post(
                f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst",
                json={"datasetId": str(uuid4())},
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "ECHO_CATALYST_HANDOFF_CONFLICT"
        assert len(_CatalystDouble.requests) == 1
        request = _CatalystDouble.requests[0]
        assert request["path"] == "/api/v1/feedback-imports"
        assert request["idempotency_key"] == f"echo-feedback:{feedback_id}:2"
        assert request["body"]["sourceRef"]["uri"].startswith("cyrene://echo/feedback-sets/")
        assert request["body"]["artifact"]["kind"] == "dataset"
        _close(app)

        restarted = create_app(
            database_path=tmp_path / "echo.sqlite3",
            artifact_root=tmp_path / "artifacts",
        )
        with TestClient(restarted) as client:
            replay = client.post(
                f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst", json={}
            )
            assert replay.status_code == 200
            assert replay.json() == receipt
        assert len(_CatalystDouble.requests) == 1
        _close(restarted)
    finally:
        stub.close()


def test_catalyst_handoff_rejects_non_201_or_mismatched_target(tmp_path: Path) -> None:
    """Only the owner's exact creation receipt may mark delivery. | 仅接受精确创建回执。"""

    target_id = str(uuid4())
    cases = [
        (
            200,
            {
                "status": "DRAFT",
                "targetResource": {
                    "uri": f"cyrene://catalyst/preparations/{target_id}",
                    "id": target_id,
                    "resourceVersion": 1,
                },
                "openIn": f"/api/v1/preparations/{target_id}",
            },
        ),
        (
            201,
            {
                "status": "DRAFT",
                "targetResource": {
                    "uri": f"cyrene://catalyst/preparations/{uuid4()}",
                    "id": target_id,
                    "resourceVersion": 1,
                },
                "openIn": f"/api/v1/preparations/{target_id}",
            },
        ),
    ]
    for index, (status, receipt) in enumerate(cases):
        _CatalystDouble.requests = []
        _CatalystDouble.response_status = status
        _CatalystDouble.receipt = receipt
        stub = _HttpStub(_CatalystDouble)
        try:
            app = create_app(
                database_path=tmp_path / f"echo-{index}.sqlite3",
                artifact_root=tmp_path / f"artifacts-{index}",
                catalyst_url=stub.url,
            )
            with TestClient(app) as client:
                feedback_id = _exported_feedback_set(client)
                response = client.post(
                    f"/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst", json={}
                )
                assert response.status_code == 502
                assert response.json()["code"] == "ECHO_CATALYST_HANDOFF_FAILED"
                persisted = client.get(f"/api/v1/feedback-sets/{feedback_id}").json()
                assert persisted["handoffStatus"] == "PREPARED"
            _close(app)
        finally:
            stub.close()

"""Standalone reference/actual imports and report lifecycle coverage."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from jsonschema import validate

from cyrene_echo import create_app
from cyrene_echo.domain import ArtifactRef, EvaluationRun, RunState, utc_now


def _jsonl(records: list[dict[str, object]]) -> bytes:
    return ("\n".join(json.dumps(record) for record in records) + "\n").encode()


def _upload(client: TestClient, content: bytes) -> dict[str, object]:
    response = client.post(
        "/api/v1/session-artifacts",
        content=content,
        headers={"Content-Type": "application/jsonl"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _suite(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/evaluation-suites",
        json={
            "name": "reference-actual-evaluation",
            "evaluator": "exact_match.v1",
            "expectedField": "reference",
            "actualField": "actual",
            "threshold": 0.5,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import_input(client: TestClient, rows: list[dict[str, object]]) -> dict[str, object]:
    artifact = _upload(client, _jsonl(rows))
    package = _upload(client, b'{"package":"candidate"}\n')
    response = client.post(
        "/api/v1/evaluation-inputs",
        json={
            "sourceRef": {
                "uri": "cyrene://data-tools/evaluation-inputs/fixture",
                "id": "fixture",
                "resourceVersion": 1,
            },
            "artifact": artifact,
            "format": "CYRENE_REFERENCE_ACTUAL_JSONL_V1",
            "contentRefs": ["cyrene://data-tools/evaluation-inputs/fixture"],
            "targetDatasetVersion": (
                "catalyst://dataset-versions/00000000-0000-4000-8000-000000000002"
            ),
            "targetPackageArtifact": package,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_reference_actual_runs_real_plugin_and_exports_bound_report(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    app = create_app(database_path=tmp_path / "echo.db", artifact_root=artifact_root)
    rows = [
        {"sampleId": "case-1", "reference": "right answer", "actual": "right answer"},
        {"sampleId": "case-2", "reference": "right answer", "actual": "wrong answer"},
        {"sampleId": "case-3", "actual": "output without reference"},
        {"sampleId": "case-4", "reference": "reference without output"},
    ]
    try:
        with TestClient(app) as client:
            evaluation_input = _import_input(client, rows)
            suite = _suite(client)
            response = client.post(
                f"/api/v1/evaluation-inputs/{evaluation_input['id']}/actions/evaluate",
                json={
                    "suiteId": suite["id"],
                    "engineBindingId": "exact-match-plugin",
                },
                headers={"Idempotency-Key": "reference-actual-first-run"},
            )
            assert response.status_code == 201, response.text
            run = response.json()
            assert run["state"] == "SUCCEEDED"

            result_response = client.get(f"/api/v1/evaluation-results/{run['resultId']}")
            assert result_response.status_code == 200, result_response.text
            result = result_response.json()
            assert result["recordCount"] == 2
            assert result["passedCount"] == 1
            assert result["metrics"]["exact_match"] == 0.5
            assert result["inputDigest"] == evaluation_input["artifact"]["digest"]

            exported = client.get(
                f"/api/v1/evaluation-results/{run['resultId']}/export"
            )
            assert exported.status_code == 200, exported.text
            assert exported.headers["content-type"].startswith("application/json")
            report = exported.json()
            report_schema = json.loads(
                (
                    Path(__file__).parents[1]
                    / "contracts/product/v1/evaluation-report.schema.json"
                ).read_text(encoding="utf-8")
            )
            validate(report, report_schema)
            assert report["schemaVersion"] == "cyrene.echo.evaluation-report.v1"
            assert report["resultId"] == run["resultId"]
            assert report["target"] == {
                "versionRef": evaluation_input["targetDatasetVersion"],
                "packageDigest": evaluation_input["targetPackageArtifact"]["digest"],
            }
            assert report["inputDigest"] == evaluation_input["artifact"]["digest"]
            assert report["evaluator"] == {"id": "exact_match.v1", "version": "1"}
            assert report["coverage"] == {
                "total": 4,
                "evaluated": 2,
                "failed": 0,
                "skipped": 2,
            }
            assert report["metrics"] == [
                {"name": "exact_match", "matched": 1, "evaluated": 2, "value": 0.5}
            ]
            assert report["samples"] == [
                {"sampleId": "case-1", "status": "EVALUATED", "exactMatch": True},
                {"sampleId": "case-2", "status": "EVALUATED", "exactMatch": False},
                {
                    "sampleId": "case-3",
                    "status": "SKIPPED",
                    "code": "MISSING_REFERENCE",
                    "message": "No reference value was supplied for this sample.",
                },
                {
                    "sampleId": "case-4",
                    "status": "SKIPPED",
                    "code": "MISSING_ACTUAL",
                    "message": "No actual value was supplied for this sample.",
                },
            ]
            assert report["failures"] == []
            assert report["skips"] == [
                {
                    "sampleId": "case-3",
                    "code": "MISSING_REFERENCE",
                    "message": "No reference value was supplied for this sample.",
                },
                {
                    "sampleId": "case-4",
                    "code": "MISSING_ACTUAL",
                    "message": "No actual value was supplied for this sample.",
                },
            ]
            assert b"right answer" not in exported.content
            assert b"wrong answer" not in exported.content
    finally:
        app.state.echo_store.close()


def test_reference_actual_all_skipped_creates_no_run_or_score(tmp_path: Path) -> None:
    app = create_app(database_path=tmp_path / "echo.db", artifact_root=tmp_path / "artifacts")
    try:
        with TestClient(app) as client:
            evaluation_input = _import_input(
                client,
                [
                    {"sampleId": "missing-reference", "actual": "output"},
                    {"sampleId": "missing-actual", "reference": "answer"},
                ],
            )
            suite = _suite(client)
            response = client.post(
                f"/api/v1/evaluation-inputs/{evaluation_input['id']}/actions/evaluate",
                json={
                    "suiteId": suite["id"],
                    "engineBindingId": "exact-match-plugin",
                },
            )
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "NO_EVALUABLE_SAMPLES"
            stored_input = client.get(
                f"/api/v1/evaluation-inputs/{evaluation_input['id']}"
            ).json()
            assert stored_input["state"] == "DRAFT"

            duplicate_rows = [
                {"sampleId": "duplicate", "reference": "a", "actual": "a"},
                {"sampleId": "duplicate", "reference": "b", "actual": "b"},
            ]
            duplicate_artifact = _upload(client, _jsonl(duplicate_rows))
            duplicate = client.post(
                "/api/v1/evaluation-inputs",
                json={
                    "sourceRef": {
                        "uri": "cyrene://data-tools/evaluation-inputs/duplicate",
                        "id": "duplicate",
                        "resourceVersion": 1,
                    },
                    "artifact": duplicate_artifact,
                    "format": "CYRENE_REFERENCE_ACTUAL_JSONL_V1",
                    "contentRefs": ["cyrene://data-tools/evaluation-inputs/duplicate"],
                    "targetDatasetVersion": "catalyst://dataset-versions/duplicate",
                    "targetPackageArtifact": duplicate_artifact,
                },
            )
            assert duplicate.status_code == 422
    finally:
        app.state.echo_store.close()


def test_restart_marks_running_run_interrupted_and_fresh_key_can_rerun(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "echo.db"
    artifact_root = tmp_path / "artifacts"
    first_app = create_app(database_path=database_path, artifact_root=artifact_root)
    stale_run_id = uuid4()
    try:
        with TestClient(first_app) as client:
            evaluation_input = _import_input(
                client,
                [{"sampleId": "restart-case", "reference": "answer", "actual": "answer"}],
            )
            suite = _suite(client)
            artifact = ArtifactRef.model_validate(evaluation_input["artifact"])
            now = utc_now()
            stale_run = EvaluationRun(
                id=stale_run_id,
                suite_id=suite["id"],
                state=RunState.RUNNING,
                input_artifact=artifact,
                engine_binding_id="exact-match-plugin",
                created_at=now,
                updated_at=now,
                resource_version=1,
            )
            first_app.state.echo_store.save("run", stale_run)
            input_id = evaluation_input["id"]
            suite_id = suite["id"]
    finally:
        first_app.state.echo_store.close()

    restarted_app = create_app(database_path=database_path, artifact_root=artifact_root)
    try:
        with TestClient(restarted_app) as client:
            interrupted = client.get(f"/api/v1/evaluation-runs/{stale_run_id}")
            assert interrupted.status_code == 200, interrupted.text
            run = interrupted.json()
            assert run["state"] == "FAILED"
            assert run["failure"]["code"] == "ECHO_RUN_INTERRUPTED_ON_RESTART"
            assert run["failure"]["retryable"] is True
            assert "No cancellation endpoint" in run["failure"]["message"]
            assert "fresh Idempotency-Key" in run["failure"]["message"]

            rerun = client.post(
                f"/api/v1/evaluation-inputs/{input_id}/actions/evaluate",
                json={"suiteId": suite_id, "engineBindingId": "exact-match-plugin"},
                headers={"Idempotency-Key": "restart-rerun-1"},
            )
            assert rerun.status_code == 201, rerun.text
            assert rerun.json()["state"] == "SUCCEEDED"
            assert rerun.json()["id"] != str(stale_run_id)
    finally:
        restarted_app.state.echo_store.close()

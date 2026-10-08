"""Regression tests for Echo hardening (Phase 1, Echo #5)."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from cyrene_echo import create_app
from cyrene_echo.domain import (
    ArtifactRef,
    EvaluationResult,
    EvaluationRun,
    GateDecision,
    GateOutcome,
    RunState,
    SampleRecord,
    utc_now,
)
from cyrene_echo.errors import EchoError
from cyrene_echo.lifecycle import LifecycleActions, SendFeedback
from cyrene_echo.store import EchoStore
from cyrene_echo.ui_page import INDEX_HTML


def test_ui_page_xss_escaping() -> None:
    """Verify that quotes are properly escaped in the client UI script to prevent attribute breakout."""
    html = INDEX_HTML
    # Check that esc function escapes quotes: " -> &quot; and ' -> &#39;
    assert '"&quot;"' in html or '&quot;' in html
    assert '&#39;' in html
    assert 'function esc(v)' in html


def test_immutable_resources_cannot_be_silently_overwritten(tmp_path: Path) -> None:
    """Verify that EvaluationResult and SampleRecord cannot be overwritten."""
    store = EchoStore(tmp_path / "echo.sqlite3")
    run_id = uuid4()
    result_id = uuid4()
    gate_id = uuid4()
    sample_id = uuid4()
    now = utc_now()

    result = EvaluationResult(
        id=result_id,
        run_id=run_id,
        score=0.9,
        metrics={},
        record_count=1,
        passed_count=1,
        report_artifact=ArtifactRef(
            uri="artifact://sha256/" + "0" * 64,
            digest="sha256:" + "0" * 64,
            size_bytes=10,
            kind="evaluation-report",
        ),
        input_digest="sha256:" + "0" * 64,
        created_at=now,
        resource_version=1,
    )
    gate = GateDecision(
        id=gate_id,
        run_id=run_id,
        result_id=result_id,
        outcome=GateOutcome.PASS,
        observed_score=0.9,
        threshold=0.8,
        created_at=now,
        resource_version=1,
    )
    run = EvaluationRun(
        id=run_id,
        suite_id=uuid4(),
        state=RunState.SUCCEEDED,
        result_id=result_id,
        gate_id=gate_id,
        input_artifact=ArtifactRef(
            uri="artifact://sha256/" + "0" * 64,
            digest="sha256:" + "0" * 64,
            size_bytes=10,
            kind="input-dataset",
        ),
        engine_binding_id="exact-match",
        created_at=now,
        updated_at=now,
        resource_version=2,
    )
    sample = SampleRecord(
        id=sample_id,
        run_id=run_id,
        sample_index=1,
        evaluator="exact_match.v1",
        input_digest="sha256:" + "0" * 64,
        input_record={"instruction": "q", "output": "a"},
        expected="a",
        actual="a",
        passed=True,
        score=1.0,
        created_at=now,
        resource_version=1,
    )

    # First save succeeds
    store.save_outcome(result, gate, run, samples=[sample])

    # Second save with same result/gate/sample IDs must raise IntegrityError, NOT silently overwrite
    modified_result = result.model_copy(update={"score": 0.1})
    with pytest.raises(sqlite3.IntegrityError):
        store.save_outcome(modified_result, gate, run, samples=[sample])

    with pytest.raises(sqlite3.IntegrityError):
        store.save_samples([sample])


def test_evaluate_bumps_input_resource_version(tmp_path: Path) -> None:
    """Verify that calling evaluate on an evaluation-input bumps its resource_version."""
    from fastapi.testclient import TestClient
    from cyrene_echo.engine import EchoArtifactPlane

    root = tmp_path / "artifacts"
    provider = EchoArtifactPlane(root)
    artifact = provider.publish_bytes(
        b'{"instruction":"q","output":"wrong","provenanceRefs":["cyrene://navigator/sessions/s"]}\n',
        kind="dataset",
    )
    app = create_app(database_path=tmp_path / "echo.db", artifact_root=root)
    with TestClient(app) as client:
        resource = client.post(
            "/api/v1/evaluation-inputs",
            json={
                "sourceRef": {
                    "uri": "cyrene://navigator/sessions/s",
                    "id": "s",
                    "resourceVersion": 1,
                },
                "artifact": artifact.model_dump(mode="json", exclude_none=True),
                "format": "NAVIGATOR_TEXT_JSONL_V1",
                "contentRefs": ["cyrene://navigator/sessions/s/events/1"],
            },
        ).json()
        assert resource["resourceRef"]["resourceVersion"] == 1

        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "review",
                "expectedField": "expected",
                "actualField": "output",
                "threshold": 1,
            },
        ).json()

        path = f"/api/v1/evaluation-inputs/{resource['id']}/actions/evaluate"
        res = client.post(path, json={
            "suiteId": suite["id"],
            "engineBindingId": "exact-match-plugin",
            "referenceAnswers": {"1": "right"},
        })
        assert res.status_code == 201

        # Check input resourceVersion is bumped to 2
        updated_input = client.get(f"/api/v1/evaluation-inputs/{resource['id']}").json()
        assert updated_input["resourceRef"]["resourceVersion"] == 2
    app.state.echo_store.close()


def test_send_feedback_lineage_limit(tmp_path: Path) -> None:
    """Verify that send_feedback rejects feedback sets with > 100 provenance references before export."""
    from fastapi.testclient import TestClient
    from cyrene_echo.engine import EchoArtifactPlane

    root = tmp_path / "artifacts"
    provider = EchoArtifactPlane(root)
    # Create 101 distinct provenance refs across samples
    lines = []
    for i in range(101):
        lines.append(f'{{"instruction":"q{i}","output":"wrong","provenanceRefs":["ref://{i}"]}}')
    payload = "\n".join(lines).encode() + b"\n"
    artifact = provider.publish_bytes(payload, kind="dataset")

    app = create_app(
        database_path=tmp_path / "echo.db",
        artifact_root=root,
        catalyst_url="http://catalyst.test",
    )
    with TestClient(app) as client:
        resource = client.post(
            "/api/v1/evaluation-inputs",
            json={
                "sourceRef": {
                    "uri": "cyrene://navigator/sessions/s",
                    "id": "s",
                    "resourceVersion": 1,
                },
                "artifact": artifact.model_dump(mode="json", exclude_none=True),
                "format": "NAVIGATOR_TEXT_JSONL_V1",
                "contentRefs": ["cyrene://navigator/sessions/s/events/1"],
            },
        ).json()

        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "review",
                "expectedField": "expected",
                "actualField": "output",
                "threshold": 1,
            },
        ).json()

        ref_answers = {str(i + 1): f"right{i}" for i in range(101)}
        run = client.post(f"/api/v1/evaluation-inputs/{resource['id']}/actions/evaluate", json={
            "suiteId": suite["id"],
            "engineBindingId": "exact-match-plugin",
            "referenceAnswers": ref_answers,
        }).json()

        # Select all 101 samples
        fb = client.post(
            "/api/v1/feedback-sets",
            json={
                "name": "too-many",
                "runId": run["id"],
                "sampleIndexes": list(range(1, 102)),
            },
        ).json()

        # send-feedback should fail with ECHO_PROVENANCE_LIMIT before exporting
        res = client.post(
            f"/api/v1/feedback-sets/{fb['id']}/actions/send-to-catalyst",
            json={"datasetId": None},
        )
        assert res.status_code == 422
        assert res.json()["code"] == "ECHO_PROVENANCE_LIMIT"
    app.state.echo_store.close()


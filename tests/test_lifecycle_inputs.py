"""Reference imports and immutable feedback regressions. | 引用导入与不可变反馈回归。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from cyrene_echo import create_app
from cyrene_echo.engine import EchoArtifactPlane


def test_reference_input_stays_draft_and_rejects_malformed_content(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    provider = EchoArtifactPlane(root)
    app = create_app(database_path=tmp_path / "echo.db", artifact_root=root)
    source = {
        "uri": "cyrene://navigator/sessions/session-a",
        "id": "session-a",
        "resourceVersion": 2,
    }
    with TestClient(app) as client:
        bad = provider.publish_bytes(b'{"output":3}\n', kind="dataset")
        payload = {
            "sourceRef": source,
            "artifact": bad.model_dump(mode="json", exclude_none=True),
            "format": "NAVIGATOR_TEXT_JSONL_V1",
            "contentRefs": [source["uri"] + "/events/1"],
        }
        assert client.post("/api/v1/evaluation-inputs", json=payload).status_code == 422
        good = provider.publish_bytes(b'{"instruction":"q","output":"wrong"}\n', kind="dataset")
        payload["artifact"] = good.model_dump(mode="json", exclude_none=True)
        headers = {"Idempotency-Key": "session-selection"}
        response = client.post("/api/v1/evaluation-inputs", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        resource = response.json()
        assert resource["state"] == "DRAFT" and "evaluationRun" not in resource
        assert (
            client.post("/api/v1/evaluation-inputs", json=payload, headers=headers).json()
            == resource
        )
        payload["sourceRef"]["resourceVersion"] = 3
        assert (
            client.post("/api/v1/evaluation-inputs", json=payload, headers=headers).status_code
            == 409
        )
        preview = client.get(f"/api/v1/evaluation-inputs/{resource['id']}/samples").json()
        assert preview["items"][0]["record"]["output"] == "wrong"
    app.state.echo_store.close()


def test_explicit_reference_review_and_frozen_feedback(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    provider = EchoArtifactPlane(root)
    original = (
        b'{"instruction":"q","output":"wrong","provenanceRefs":["cyrene://navigator/sessions/s"]}\n'
    )
    artifact = provider.publish_bytes(original, kind="dataset")
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
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "review",
                "expectedField": "expected",
                "actualField": "output",
                "threshold": 1,
            },
        ).json()
        command = {
            "suiteId": suite["id"],
            "engineBindingId": "exact-match-plugin",
            "referenceAnswers": {"2": "right"},
        }
        path = f"/api/v1/evaluation-inputs/{resource['id']}/actions/evaluate"
        assert client.post(path, json=command).status_code == 422
        command["referenceAnswers"] = {"1": "right"}
        response = client.post(path, json=command)
        assert response.status_code == 201, response.text
        run = response.json()
        assert run["state"] == "SUCCEEDED"
        assert client.post(path, json=command).json()["id"] == run["id"]
        assert provider.resolve(artifact).read_bytes() == original
        annotation_path = f"/api/v1/evaluation-runs/{run['id']}/annotations"
        annotation = client.post(
            annotation_path,
            json={
                "sampleIndex": 1,
                "reviewer": "reviewer",
                "correctedOutput": "right",
                "manualScore": 1,
            },
        ).json()
        feedback = client.post(
            "/api/v1/feedback-sets",
            json={
                "name": "selected",
                "runId": run["id"],
                "sampleIndexes": [1],
                "annotationIds": [annotation["id"]],
            },
        ).json()
        export_path = f"/api/v1/feedback-sets/{feedback['id']}/export"
        first = client.post(export_path).json()
        exported = client.get(export_path).content
        client.post(
            annotation_path,
            json={
                "sampleIndex": 1,
                "reviewer": "later",
                "correctedOutput": "different",
                "manualScore": 0,
            },
        )
        assert client.post(export_path).json() == first
        assert client.get(export_path).content == exported
        row = json.loads(exported)
        assert row["output"] == "right" and row["modelOutput"] == "wrong"
        assert row["humanAnnotation"]["id"] == annotation["id"]
        assert row["evaluationScore"] == 0
    app.state.echo_store.close()

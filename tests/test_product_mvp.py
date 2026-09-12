"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 test_product_mvp.py                                             │
│  Module: tests.test_product_mvp                                     │
│  Role: Evaluation, gate, failure, idempotency, restart acceptance.  │
│                                                                     │
│  模块职责：验证评估、门禁、失败持久化、幂等与重启恢复。                      │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker, validate
from openapi_spec_validator.readers import read_from_filename
from referencing import Registry, Resource

from cyrene_echo import create_app
from cyrene_echo.domain import ArtifactRef
from cyrene_echo.engine import sha256_file


def _artifact(path: Path, artifact_root: Path) -> dict[str, Any]:
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


def test_artifact_kind_remains_producer_owned() -> None:
    digest = "sha256:" + "a" * 64
    artifact = ArtifactRef(
        uri="artifact://sha256/" + "a" * 64,
        digest=digest,
        size_bytes=0,
        kind="echo.evaluation.snapshot.v2",
    )

    assert artifact.kind == "echo.evaluation.snapshot.v2"


def test_runtime_paths_match_frozen_openapi(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    contract, _ = read_from_filename(
        str(Path(__file__).parents[1] / "contracts/product/v1/openapi.yaml")
    )
    assert set(app.openapi()["paths"]) == set(contract["paths"])
    _close(app)


def test_evaluation_gate_and_restart(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_text(
        '{"expected":"yes","actual":"yes"}\n{"expected":"yes","actual":"no"}\n',
        encoding="utf-8",
    )
    database = tmp_path / "echo.sqlite3"
    artifacts = tmp_path / "artifacts"
    app = create_app(
        database_path=database,
        artifact_root=artifacts,
    )

    with TestClient(app) as client:
        suite = client.post(
            "/api/v1/evaluation-suites",
            headers={"Idempotency-Key": "suite-demo"},
            json={
                "name": "exactness",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 0.5,
            },
        ).json()
        response = client.post(
            "/api/v1/evaluation-runs",
            headers={"Idempotency-Key": "run-demo"},
            json={
                "suiteId": suite["id"],
                "inputArtifact": _artifact(source, artifacts),
                "engineBindingId": "exact-match-plugin",
            },
        )
        assert response.status_code == 201
        run = response.json()
        assert run["state"] == "SUCCEEDED"
        result = client.get(f"/api/v1/evaluation-results/{run['resultId']}").json()
        gate = client.get(f"/api/v1/gate-decisions/{run['gateId']}").json()
        assert result["score"] == 0.5
        assert result["recordCount"] == 2
        assert result["passedCount"] == 1
        assert result["inputDigest"] == run["inputArtifact"]["digest"]
        assert gate["outcome"] == "PASS"

        replay = client.post(
            "/api/v1/evaluation-runs",
            headers={"Idempotency-Key": "run-demo"},
            json={
                "suiteId": suite["id"],
                "inputArtifact": _artifact(source, artifacts),
                "engineBindingId": "exact-match-plugin",
            },
        )
        assert replay.json()["id"] == run["id"]

    _close(app)
    restarted = create_app(
        database_path=database,
        artifact_root=artifacts,
    )
    with TestClient(restarted) as client:
        assert client.get(f"/api/v1/evaluation-runs/{run['id']}").json() == run
        assert client.get(f"/api/v1/evaluation-results/{result['id']}").json() == result
        assert client.get(f"/api/v1/gate-decisions/{gate['id']}").json() == gate

    contract_root = Path(__file__).parents[1] / "contracts/product/v1"
    run_schema_path = contract_root / "evaluation-run.schema.json"
    run_schema = json.loads(run_schema_path.read_text())
    artifact_schema = json.loads(
        (contract_root / "generated/platform/artifact-ref.schema.json").read_text()
    )
    registry = Registry().with_resource(
        artifact_schema["$id"], Resource.from_contents(artifact_schema)
    )
    Draft202012Validator(
        run_schema,
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(run)
    result_schema = json.loads((contract_root / "evaluation-result.schema.json").read_text())
    Draft202012Validator(
        result_schema,
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(result)
    gate_schema = json.loads((contract_root / "gate-decision.schema.json").read_text())
    validate(instance=gate, schema=gate_schema, format_checker=FormatChecker())
    _close(restarted)


def test_gate_fail_is_not_run_failure(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_text('{"expected":1,"actual":0}\n', encoding="utf-8")
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    with TestClient(app) as client:
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "strict",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 1.0,
            },
        ).json()
        run = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": _artifact(source, tmp_path / "artifacts"),
                "engineBindingId": "exact-match-plugin",
            },
        ).json()
        gate = client.get(f"/api/v1/gate-decisions/{run['gateId']}").json()
        assert run["state"] == "SUCCEEDED"
        assert gate["outcome"] == "FAIL"
    _close(app)


def test_malformed_jsonl_persists_failed_run(tmp_path: Path) -> None:
    source = tmp_path / "broken.jsonl"
    source.write_text('{"expected": [}\n', encoding="utf-8")
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
        command = {
            "suiteId": suite["id"],
            "inputArtifact": _artifact(source, tmp_path / "artifacts"),
            "engineBindingId": "exact-match-plugin",
        }
        response = client.post(
            "/api/v1/evaluation-runs",
            headers={"Idempotency-Key": "broken-run"},
            json=command,
        )
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")
        problem = response.json()
        assert problem["code"] == "ECHO_EVALUATION_FAILED"
        persisted = client.get(problem["resourceRef"]).json()
        assert persisted["state"] == "FAILED"
        assert persisted["failure"]["code"] == "ECHO_EVALUATION_FAILED"

        replay = client.post(
            "/api/v1/evaluation-runs",
            headers={"Idempotency-Key": "broken-run"},
            json=command,
        )
        assert replay.status_code == 201
        assert replay.json() == persisted
    _close(app)


def test_unresolved_artifact_identity_is_denied_without_path_leak(tmp_path: Path) -> None:
    source = tmp_path / "outside.jsonl"
    source.write_text('{"expected":1,"actual":1}\n', encoding="utf-8")
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "isolated-artifacts",
    )
    with TestClient(app) as client:
        suite = client.post(
            "/api/v1/evaluation-suites",
            json={
                "name": "scope",
                "expectedField": "expected",
                "actualField": "actual",
                "threshold": 1,
            },
        ).json()
        response = client.post(
            "/api/v1/evaluation-runs",
            json={
                "suiteId": suite["id"],
                "inputArtifact": {
                    "uri": f"artifact://sha256/{'f' * 64}",
                    "digest": f"sha256:{'f' * 64}",
                    "size_bytes": source.stat().st_size,
                    "kind": "dataset",
                },
                "engineBindingId": "exact-match-plugin",
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "ECHO_ARTIFACT_UNAVAILABLE"
        assert str(source) not in response.text
    _close(app)

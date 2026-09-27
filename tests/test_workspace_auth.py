"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 test_workspace_auth.py                                          │
│  Module: tests.test_workspace_auth                                  │
│  Role: Workspace token, scope isolation, and migration acceptance.  │
│                                                                     │
│  模块职责：验证 Workspace 凭据、隔离边界与旧库迁移。                    │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from cyrene_echo import create_app
from cyrene_echo.domain import (
    ArtifactRef,
    CreateSuiteRequest,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    FeedbackSet,
    GateDecision,
    HumanAnnotation,
    RunState,
    SampleRecord,
    utc_now,
)
from cyrene_echo.service import request_hash
from cyrene_echo.workspace_auth import (
    WorkspaceServiceAuthConfigError,
    WorkspaceServiceAuthenticator,
    WorkspaceServicePrincipal,
)

TOKEN_A = "echo-workspace-a-token-" + "a" * 40
TOKEN_A_ROTATED = "echo-workspace-a-token-" + "b" * 40
TOKEN_B = "echo-workspace-b-token-" + "c" * 40


def _auth_config(*tokens: tuple[str, str, str]) -> str:
    return json.dumps(
        [
            {
                "tokenSha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
                "organizationId": organization_id,
                "workspaceId": workspace_id,
            }
            for token, organization_id, workspace_id in tokens
        ]
    )


def _app(tmp_path: Path, auth_config: str | None = None):
    return create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
        workspace_authenticator=WorkspaceServiceAuthenticator.from_json(auth_config),
    )


def _close(app) -> None:
    app.state.echo_store.close()


def _suite_command(**updates: object) -> dict[str, object]:
    command: dict[str, object] = {
        "name": "workspace-suite",
        "evaluator": "exact_match.v1",
        "expectedField": "expected",
        "actualField": "actual",
        "threshold": 0.5,
    }
    command.update(updates)
    return command


def test_workspace_authenticator_supports_rotation_and_rejects_bad_maps() -> None:
    authenticator = WorkspaceServiceAuthenticator.from_json(
        _auth_config(
            (TOKEN_A, "org-a", "workspace-a"),
            (TOKEN_A_ROTATED, "org-a", "workspace-a"),
        )
    )

    expected = WorkspaceServicePrincipal("org-a", "workspace-a")
    assert authenticator.authenticate(f"Bearer {TOKEN_A}") == expected
    assert authenticator.authenticate(f"Bearer {TOKEN_A_ROTATED}") == expected
    assert authenticator.authenticate(f"Bearer {'x' * 31}") is None
    assert authenticator.authenticate(f"Bearer {TOKEN_B}") is None
    assert not WorkspaceServiceAuthenticator.from_json(None).configured

    with pytest.raises(WorkspaceServiceAuthConfigError):
        WorkspaceServiceAuthenticator.from_json("not-json")
    with pytest.raises(WorkspaceServiceAuthConfigError):
        WorkspaceServiceAuthenticator.from_json(
            _auth_config((TOKEN_A, "org-a", "workspace-a"), (TOKEN_A, "org-b", "workspace-b"))
        )


def test_private_suites_fail_closed_and_partition_reads_and_replays(tmp_path: Path) -> None:
    app = _app(
        tmp_path,
        _auth_config(
            (TOKEN_A, "org-a", "workspace-a"),
            (TOKEN_A_ROTATED, "org-a", "workspace-a"),
            (TOKEN_B, "org-b", "workspace-b"),
        ),
    )
    headers_a = {"Authorization": f"Bearer {TOKEN_A}"}
    headers_a_rotated = {"Authorization": f"Bearer {TOKEN_A_ROTATED}"}
    headers_b = {"Authorization": f"Bearer {TOKEN_B}"}
    private_collection = "/internal/workspace/v1/evaluation-suites"

    try:
        with TestClient(app) as client:
            assert client.post(private_collection, json=_suite_command()).status_code == 401
            assert (
                client.post(
                    private_collection,
                    headers={"Authorization": f"Bearer {'x' * 31}"},
                    json=_suite_command(),
                ).status_code
                == 401
            )

            first = client.post(
                private_collection,
                headers={**headers_a, "Idempotency-Key": "shared-key"},
                json=_suite_command(),
            )
            assert first.status_code == 201, first.text
            first_id = first.json()["id"]
            replay = client.post(
                private_collection,
                headers={**headers_a_rotated, "Idempotency-Key": "shared-key"},
                json=_suite_command(),
            )
            assert replay.status_code == 201
            assert replay.json()["id"] == first_id

            conflict = client.post(
                private_collection,
                headers={**headers_a, "Idempotency-Key": "shared-key"},
                json=_suite_command(name="changed"),
            )
            assert conflict.status_code == 409

            second = client.post(
                private_collection,
                headers={**headers_b, "Idempotency-Key": "shared-key"},
                json=_suite_command(),
            )
            assert second.status_code == 201, second.text
            second_id = second.json()["id"]
            assert second_id != first_id

            assert (
                client.get(f"{private_collection}/{first_id}", headers=headers_a).status_code == 200
            )
            assert (
                client.get(
                    f"{private_collection}/{first_id}", headers=headers_a_rotated
                ).status_code
                == 200
            )
            assert (
                client.get(f"{private_collection}/{first_id}", headers=headers_b).status_code == 404
            )
            assert client.get(f"/api/v1/evaluation-suites/{first_id}").status_code == 404

            legacy = client.post(
                "/api/v1/evaluation-suites",
                headers={"Idempotency-Key": "shared-key"},
                json=_suite_command(name="legacy-suite"),
            )
            assert legacy.status_code == 201
            legacy_id = legacy.json()["id"]
            assert client.get(f"/api/v1/evaluation-suites/{legacy_id}").status_code == 200
            assert (
                client.get(f"{private_collection}/{legacy_id}", headers=headers_a).status_code
                == 404
            )
            assert "/internal/workspace/v1/evaluation-suites" not in app.openapi()["paths"]

            forged_scope = client.post(
                private_collection,
                headers=headers_a,
                json=_suite_command(organizationId="org-b", workspaceId="workspace-b"),
            )
            assert forged_scope.status_code == 422
    finally:
        _close(app)


def test_missing_private_auth_configuration_returns_503_without_changing_legacy_api(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    try:
        with TestClient(app) as client:
            private = client.get(
                "/internal/workspace/v1/evaluation-suites/00000000-0000-0000-0000-000000000001"
            )
            assert private.status_code == 503
            legacy = client.post(
                "/api/v1/evaluation-suites",
                json=_suite_command(name="legacy-only"),
            )
            assert legacy.status_code == 201
            assert client.get(f"/api/v1/evaluation-suites/{legacy.json()['id']}").status_code == 200
    finally:
        _close(app)


def test_workspace_suite_rejects_unscoped_judge_profile_references(tmp_path: Path) -> None:
    app = _app(tmp_path, _auth_config((TOKEN_A, "org-a", "workspace-a")))
    try:
        with TestClient(app) as client:
            profile = client.post(
                "/api/v1/judge-profiles",
                json={
                    "name": "legacy-profile",
                    "judgeModel": "model",
                    "exchangeEndpointRef": "endpoint://legacy",
                    "promptTemplate": "score this",
                },
            )
            assert profile.status_code == 201

            referenced = client.post(
                "/internal/workspace/v1/evaluation-suites",
                headers={"Authorization": f"Bearer {TOKEN_A}"},
                json=_suite_command(judgeProfileId=profile.json()["id"]),
            )
            assert referenced.status_code == 403
            assert referenced.json()["code"] == "ECHO_WORKSPACE_JUDGE_PROFILE_SCOPE_REQUIRED"

            missing = client.post(
                "/internal/workspace/v1/evaluation-suites",
                headers={"Authorization": f"Bearer {TOKEN_A}"},
                json=_suite_command(evaluator="llm_judge.v1"),
            )
            assert missing.status_code == 422
    finally:
        _close(app)


def test_legacy_run_result_gate_and_feedback_reads_hide_private_suite_lineage(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path, _auth_config((TOKEN_A, "org-a", "workspace-a")))
    artifact_digest = "a" * 64
    artifact = ArtifactRef(
        uri=f"artifact://sha256/{artifact_digest}",
        digest=f"sha256:{artifact_digest}",
        size_bytes=0,
        kind="dataset",
    )
    now = utc_now()

    try:
        with TestClient(app) as client:
            suite_response = client.post(
                "/internal/workspace/v1/evaluation-suites",
                headers={"Authorization": f"Bearer {TOKEN_A}"},
                json=_suite_command(),
            )
            assert suite_response.status_code == 201, suite_response.text
            suite_id = suite_response.json()["id"]
            assert (
                client.post(
                    "/api/v1/evaluation-runs",
                    json={
                        "suiteId": suite_id,
                        "inputArtifact": artifact.model_dump(mode="json"),
                        "engineBindingId": "exact-match-plugin",
                    },
                ).status_code
                == 404
            )

            run_id, result_id, gate_id = uuid4(), uuid4(), uuid4()
            sample_id, annotation_id, feedback_id = uuid4(), uuid4(), uuid4()
            run = EvaluationRun(
                id=run_id,
                suite_id=suite_id,
                state=RunState.SUCCEEDED,
                input_artifact=artifact,
                engine_binding_id="exact-match-plugin",
                result_id=result_id,
                gate_id=gate_id,
                created_at=now,
                updated_at=now,
                resource_version=1,
            )
            result = EvaluationResult(
                id=result_id,
                run_id=run_id,
                score=1.0,
                metrics={"score": 1.0},
                record_count=1,
                passed_count=1,
                report_artifact=artifact,
                input_digest=artifact.digest,
                created_at=now,
                resource_version=1,
            )
            gate = GateDecision(
                id=gate_id,
                run_id=run_id,
                result_id=result_id,
                outcome="PASS",
                observed_score=1.0,
                threshold=0.5,
                created_at=now,
                resource_version=1,
            )
            sample = SampleRecord(
                id=sample_id,
                run_id=run_id,
                sample_index=1,
                evaluator="exact_match.v1",
                input_digest=artifact.digest,
                input_record={"expected": "yes", "actual": "yes"},
                passed=True,
                score=1.0,
                created_at=now,
                resource_version=1,
            )
            annotation = HumanAnnotation(
                id=annotation_id,
                run_id=run_id,
                sample_index=1,
                reviewer="reviewer",
                manual_score=1.0,
                created_at=now,
                updated_at=now,
                resource_version=1,
            )
            feedback = FeedbackSet(
                id=feedback_id,
                name="legacy-child-of-private-suite",
                run_id=run_id,
                sample_indexes=[1],
                annotation_ids=[annotation_id],
                created_at=now,
                updated_at=now,
                resource_version=1,
            )
            children = [
                ("run", run),
                ("result", result),
                ("gate", gate),
                ("sample", sample),
                ("annotation", annotation),
                ("feedback_set", feedback),
            ]
            store = app.state.echo_store
            with store._lock, store._connection:
                store._connection.executemany(
                    "INSERT INTO resources(kind, id, document) VALUES (?, ?, ?)",
                    [
                        (
                            kind,
                            str(resource.id),
                            resource.model_dump_json(by_alias=True, exclude_none=True),
                        )
                        for kind, resource in children
                    ],
                )

            assert client.get(f"/api/v1/evaluation-runs/{run_id}").status_code == 404
            assert client.get(f"/api/v1/evaluation-results/{result_id}").status_code == 404
            assert client.get(f"/api/v1/gate-decisions/{gate_id}").status_code == 404
            assert client.get(f"/api/v1/evaluation-runs/{run_id}/samples").status_code == 404
            assert client.get(f"/api/v1/evaluation-runs/{run_id}/samples/1").status_code == 404
            assert client.get(f"/api/v1/evaluation-runs/{run_id}/annotations").status_code == 404
            assert (
                client.post(
                    f"/api/v1/evaluation-runs/{run_id}/annotations",
                    json={"sampleIndex": 1, "reviewer": "other"},
                ).status_code
                == 404
            )
            assert client.get("/api/v1/feedback-sets").json() == []
            assert client.get(f"/api/v1/feedback-sets?runId={run_id}").json() == []
            assert client.get(f"/api/v1/feedback-sets/{feedback_id}").status_code == 404
            assert client.post(f"/api/v1/feedback-sets/{feedback_id}/export").status_code == 404
            assert client.get(f"/api/v1/feedback-sets/{feedback_id}/export").status_code == 404
    finally:
        _close(app)


def test_historical_rows_remain_legacy_only_after_scope_migration(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    now = datetime(2024, 1, 1, tzinfo=UTC)
    request = CreateSuiteRequest(
        name="historical-suite",
        evaluator="exact_match.v1",
        expected_field="expected",
        actual_field="actual",
        threshold=0.5,
    )
    suite = EvaluationSuite(
        id=uuid4(),
        name=request.name,
        evaluator=request.evaluator,
        expected_field=request.expected_field,
        actual_field=request.actual_field,
        threshold=request.threshold,
        created_at=now,
        updated_at=now,
        resource_version=1,
    )
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE resources(kind TEXT NOT NULL, id TEXT NOT NULL, document TEXT NOT NULL,
            PRIMARY KEY(kind, id));
        CREATE TABLE idempotency(scope TEXT NOT NULL, key TEXT NOT NULL,
            request_hash TEXT NOT NULL, resource_id TEXT NOT NULL, PRIMARY KEY(scope, key));
        """
    )
    connection.execute(
        "INSERT INTO resources(kind, id, document) VALUES ('suite', ?, ?)",
        (str(suite.id), suite.model_dump_json(by_alias=True, exclude_none=True)),
    )
    connection.execute(
        "INSERT INTO idempotency(scope, key, request_hash, resource_id) "
        "VALUES ('create-suite', 'historical-key', ?, ?)",
        (request_hash(request), str(suite.id)),
    )
    connection.commit()
    connection.close()

    app = create_app(
        database_path=database,
        artifact_root=tmp_path / "artifacts",
        workspace_authenticator=WorkspaceServiceAuthenticator.from_json(
            _auth_config((TOKEN_A, "org-a", "workspace-a"))
        ),
    )
    try:
        with TestClient(app) as client:
            legacy_replay = client.post(
                "/api/v1/evaluation-suites",
                headers={"Idempotency-Key": "historical-key"},
                json=_suite_command(name=request.name),
            )
            assert legacy_replay.status_code == 201
            assert legacy_replay.json()["id"] == str(suite.id)
            assert client.get(f"/api/v1/evaluation-suites/{suite.id}").status_code == 200

            private_get = client.get(
                f"/internal/workspace/v1/evaluation-suites/{suite.id}",
                headers={"Authorization": f"Bearer {TOKEN_A}"},
            )
            assert private_get.status_code == 404
            private_create = client.post(
                "/internal/workspace/v1/evaluation-suites",
                headers={
                    "Authorization": f"Bearer {TOKEN_A}",
                    "Idempotency-Key": "historical-key",
                },
                json=_suite_command(name=request.name),
            )
            assert private_create.status_code == 201
            assert private_create.json()["id"] != str(suite.id)
    finally:
        _close(app)

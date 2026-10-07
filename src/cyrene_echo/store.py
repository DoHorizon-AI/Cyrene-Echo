"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 store.py                                                        │
│  Module: cyrene_echo.store                                          │
│  Role: SQLite Product resource authority and idempotency ledger.     │
│                                                                     │
│  模块职责：持久化 Echo 产品资源与幂等账本（含样本、标注与反馈集）。        │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from uuid import UUID

from cyrene_echo.domain import (
    EvaluationInput,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    FeedbackHandoff,
    FeedbackSet,
    GateDecision,
    HumanAnnotation,
    JudgeProfile,
    ProductFailure,
    RunState,
    SampleRecord,
    utc_now,
)
from cyrene_echo.errors import EchoError
from cyrene_echo.workspace_auth import WorkspaceServicePrincipal


class EchoStore:
    """Durable resource store independent of evaluator state. | 独立于评估器的资源存储。"""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS resources (
                    kind TEXT NOT NULL,
                    id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    organization_id TEXT,
                    workspace_id TEXT,
                    PRIMARY KEY(kind, id)
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    scope TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    PRIMARY KEY(scope, organization_id, workspace_id, key)
                );
                CREATE INDEX IF NOT EXISTS idx_resources_kind_run
                    ON resources(kind, id);
                """
            )
        self._migrate_workspace_scope_schema()

    def _migrate_workspace_scope_schema(self) -> None:
        """Add Workspace ownership and preserve old rows as unscoped."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                resource_columns = {
                    str(row["name"])
                    for row in self._connection.execute("PRAGMA table_info(resources)")
                }
                if "organization_id" not in resource_columns:
                    self._connection.execute(
                        "ALTER TABLE resources ADD COLUMN organization_id TEXT"
                    )
                if "workspace_id" not in resource_columns:
                    self._connection.execute("ALTER TABLE resources ADD COLUMN workspace_id TEXT")

                idempotency_info = list(self._connection.execute("PRAGMA table_info(idempotency)"))
                idempotency_columns = {str(row["name"]) for row in idempotency_info}
                primary_key = [
                    str(row["name"])
                    for row in sorted(idempotency_info, key=lambda item: int(item["pk"]))
                    if int(row["pk"]) > 0
                ]
                expected_primary_key = ["scope", "organization_id", "workspace_id", "key"]
                if (
                    not {"organization_id", "workspace_id"}.issubset(idempotency_columns)
                    or primary_key != expected_primary_key
                ):
                    organization_expr = (
                        "organization_id" if "organization_id" in idempotency_columns else "''"
                    )
                    workspace_expr = (
                        "workspace_id" if "workspace_id" in idempotency_columns else "''"
                    )
                    self._connection.execute(
                        """
                        CREATE TABLE idempotency_workspace_new (
                            scope TEXT NOT NULL,
                            organization_id TEXT NOT NULL,
                            workspace_id TEXT NOT NULL,
                            key TEXT NOT NULL,
                            request_hash TEXT NOT NULL,
                            resource_id TEXT NOT NULL,
                            PRIMARY KEY(scope, organization_id, workspace_id, key)
                        )
                        """
                    )
                    migration_sql = f"""
                        INSERT INTO idempotency_workspace_new(
                            scope, organization_id, workspace_id, key, request_hash, resource_id
                        )
                        SELECT scope, {organization_expr}, {workspace_expr}, key,
                               request_hash, resource_id
                        FROM idempotency
                        """
                    self._connection.execute(migration_sql)
                    self._connection.execute("DROP TABLE idempotency")
                    self._connection.execute(
                        "ALTER TABLE idempotency_workspace_new RENAME TO idempotency"
                    )

                self._connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_resources_workspace_scope "
                    "ON resources(kind, organization_id, workspace_id, id)"
                )
                self._connection.execute("PRAGMA user_version = 1")
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        """Close the database connection. | 关闭数据库连接。"""

        with self._lock:
            self._connection.close()

    def save(
        self,
        kind: str,
        resource: EvaluationSuite
        | EvaluationRun
        | EvaluationResult
        | GateDecision
        | JudgeProfile
        | SampleRecord
        | HumanAnnotation
        | FeedbackSet
        | FeedbackHandoff
        | EvaluationInput,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> None:
        """Upsert one typed resource document. | 写入一个类型化资源文档。"""

        resource_id = str(resource.id)
        document = resource.model_dump_json(by_alias=True, exclude_none=True)
        organization_id = principal.organization_id if principal else None
        workspace_id = principal.workspace_id if principal else None
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO resources("
                "kind, id, document, organization_id, workspace_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (kind, resource_id, document, organization_id, workspace_id),
            )

    def create_workspace_suite(
        self,
        suite: EvaluationSuite,
        principal: WorkspaceServicePrincipal,
        idempotency_key: str | None,
        digest: str,
    ) -> EvaluationSuite:
        """Atomically persist a scoped suite and its scoped replay record."""

        document = suite.model_dump_json(by_alias=True, exclude_none=True)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key is not None:
                    replay = self._connection.execute(
                        "SELECT request_hash, resource_id FROM idempotency "
                        "WHERE scope = 'create-suite' AND organization_id = ? "
                        "AND workspace_id = ? AND key = ?",
                        (principal.organization_id, principal.workspace_id, idempotency_key),
                    ).fetchone()
                    if replay is not None:
                        if replay["request_hash"] != digest:
                            raise EchoError(
                                code="ECHO_IDEMPOTENCY_CONFLICT",
                                title="Idempotency key conflict",
                                detail=(
                                    "The Idempotency-Key was already used with a different "
                                    "request body."
                                ),
                                status=409,
                            )
                        scoped_suite = self._connection.execute(
                            "SELECT document FROM resources WHERE kind = 'suite' AND id = ? "
                            "AND organization_id = ? AND workspace_id = ?",
                            (
                                str(replay["resource_id"]),
                                principal.organization_id,
                                principal.workspace_id,
                            ),
                        ).fetchone()
                        if scoped_suite is None:
                            raise EchoError(
                                code="ECHO_STATE_CORRUPT",
                                title="Product state is inconsistent",
                                detail=(
                                    "The idempotency ledger references a missing EvaluationSuite."
                                ),
                                status=500,
                            )
                        result = EvaluationSuite.model_validate_json(scoped_suite["document"])
                        self._connection.commit()
                        return result

                self._connection.execute(
                    "INSERT INTO resources(kind, id, document, organization_id, workspace_id) "
                    "VALUES ('suite', ?, ?, ?, ?)",
                    (
                        str(suite.id),
                        document,
                        principal.organization_id,
                        principal.workspace_id,
                    ),
                )
                if idempotency_key is not None:
                    self._connection.execute(
                        "INSERT INTO idempotency("
                        "scope, organization_id, workspace_id, key, request_hash, resource_id) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            "create-suite",
                            principal.organization_id,
                            principal.workspace_id,
                            idempotency_key,
                            digest,
                            str(suite.id),
                        ),
                    )
                self._connection.commit()
                return suite
            except Exception:
                self._connection.rollback()
                raise

    def save_outcome(
        self,
        result: EvaluationResult,
        gate: GateDecision,
        run: EvaluationRun,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> None:
        """Atomically commit result, gate, then terminal run. | 原子提交结果、门禁与运行。"""

        documents = [
            ("result", str(result.id), result.model_dump_json(by_alias=True, exclude_none=True)),
            ("gate", str(gate.id), gate.model_dump_json(by_alias=True, exclude_none=True)),
            ("run", str(run.id), run.model_dump_json(by_alias=True, exclude_none=True)),
        ]
        with self._lock, self._connection:
            organization_id = principal.organization_id if principal else None
            workspace_id = principal.workspace_id if principal else None
            self._connection.executemany(
                "INSERT OR REPLACE INTO resources("
                "kind, id, document, organization_id, workspace_id) VALUES (?, ?, ?, ?, ?)",
                [(*row, organization_id, workspace_id) for row in documents],
            )

    def save_samples(
        self,
        samples: list[SampleRecord],
        principal: WorkspaceServicePrincipal | None = None,
    ) -> None:
        """Persist per-sample records for one run. | 持久化逐样本记录。"""

        if not samples:
            return
        organization_id = principal.organization_id if principal else None
        workspace_id = principal.workspace_id if principal else None
        rows = [
            (
                "sample",
                str(sample.id),
                sample.model_dump_json(by_alias=True, exclude_none=True),
                organization_id,
                workspace_id,
            )
            for sample in samples
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO resources("
                "kind, id, document, organization_id, workspace_id) VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def _get(
        self,
        kind: str,
        resource_id: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> str | None:
        with self._lock:
            if principal is None:
                row = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = ? AND id = ? "
                    "AND organization_id IS NULL AND workspace_id IS NULL",
                    (kind, str(resource_id)),
                ).fetchone()
            else:
                row = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = ? AND id = ? "
                    "AND organization_id = ? AND workspace_id = ?",
                    (kind, str(resource_id), principal.organization_id, principal.workspace_id),
                ).fetchone()
        return str(row["document"]) if row else None

    def get_suite(
        self,
        resource_id: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> EvaluationSuite | None:
        """Read an EvaluationSuite. | 读取 EvaluationSuite。"""

        with self._lock:
            if principal is None:
                row = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = 'suite' AND id = ? "
                    "AND organization_id IS NULL AND workspace_id IS NULL",
                    (str(resource_id),),
                ).fetchone()
            else:
                row = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = 'suite' AND id = ? "
                    "AND organization_id = ? AND workspace_id = ?",
                    (str(resource_id), principal.organization_id, principal.workspace_id),
                ).fetchone()
        document = str(row["document"]) if row else None
        return EvaluationSuite.model_validate_json(document) if document else None

    def get_input(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> EvaluationInput | None:
        """Read an evaluation preparation. | 读取评估准备资源。"""
        document = self._get("input", resource_id, principal)
        return EvaluationInput.model_validate_json(document) if document else None

    def list_inputs(
        self, principal: WorkspaceServicePrincipal | None = None
    ) -> list[EvaluationInput]:
        """List drafts for independent discovery. | 列出可独立发现的草稿。"""
        with self._lock:
            if principal is None:
                rows = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = 'input' "
                    "AND organization_id IS NULL AND workspace_id IS NULL ORDER BY rowid DESC"
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = 'input' "
                    "AND organization_id = ? AND workspace_id = ? ORDER BY rowid DESC",
                    (principal.organization_id, principal.workspace_id),
                ).fetchall()
        return [EvaluationInput.model_validate_json(row["document"]) for row in rows]

    def create_input(
        self,
        resource: EvaluationInput,
        key: str,
        digest: str,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> EvaluationInput:
        """Atomically persist an immutable input and its handoff receipt. | 原子保存输入。"""
        with self._lock, self._connection:
            replay = self.resolve_idempotency("import-input", key, digest, principal)
            if replay is not None:
                existing = self.get_input(UUID(replay), principal)
                if existing is None:
                    raise EchoError(
                        code="ECHO_INPUT_RECEIPT_INVALID",
                        title="Input receipt invalid",
                        detail="The persisted handoff receipt has no target resource.",
                        status=500,
                    )
                return existing
            organization_id = principal.organization_id if principal else None
            workspace_id = principal.workspace_id if principal else None
            self._connection.execute(
                "INSERT INTO resources(kind, id, document, organization_id, workspace_id) "
                "VALUES ('input', ?, ?, ?, ?)",
                (
                    str(resource.id),
                    resource.model_dump_json(exclude_none=True),
                    organization_id,
                    workspace_id,
                ),
            )
            self._connection.execute(
                "INSERT INTO idempotency("
                "scope, organization_id, workspace_id, key, request_hash, resource_id) "
                "VALUES ('import-input', ?, ?, ?, ?, ?)",
                (
                    principal.organization_id if principal else "",
                    principal.workspace_id if principal else "",
                    key,
                    digest,
                    str(resource.id),
                ),
            )
        return resource

    def get_run(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> EvaluationRun | None:
        """Read an EvaluationRun. | 读取 EvaluationRun。"""

        document = self._get("run", resource_id, principal)
        run = EvaluationRun.model_validate_json(document) if document else None
        if run is not None and self.get_suite(run.suite_id, principal) is None:
            return None
        return run

    def list_active_activity_tasks(self) -> list[dict[str, str]]:
        """Return running evaluation runs for startup gate reconciliation."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT document FROM resources WHERE kind = 'run' ORDER BY rowid"
            ).fetchall()
        runs = [EvaluationRun.model_validate_json(row["document"]) for row in rows]
        return [
            {"task_id": str(run.id), "state": "RUNNING"}
            for run in runs
            if run.state.value == "RUNNING"
        ]

    def interrupt_running_runs(self) -> int:
        """Persist leftover RUNNING runs as interrupted after a process restart."""

        interrupted = 0
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT id, document FROM resources WHERE kind = 'run'"
            ).fetchall()
            for row in rows:
                run = EvaluationRun.model_validate_json(row["document"])
                if run.state.value != "RUNNING":
                    continue
                terminal = run.model_copy(
                    update={
                        "state": RunState.FAILED,
                        "failure": ProductFailure(
                            code="ECHO_RUN_INTERRUPTED_ON_RESTART",
                            message=(
                                "The Echo process restarted while this bounded synchronous run "
                                "was active. No cancellation endpoint is available. Start a new "
                                "run with a fresh Idempotency-Key after checking the input."
                            ),
                            retryable=True,
                        ),
                        "updated_at": utc_now(),
                        "resource_version": run.resource_version + 1,
                    }
                )
                self._connection.execute(
                    "UPDATE resources SET document = ? WHERE kind = 'run' AND id = ?",
                    (terminal.model_dump_json(by_alias=True, exclude_none=True), row["id"]),
                )
                interrupted += 1
        return interrupted

    def get_result(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> EvaluationResult | None:
        """Read an EvaluationResult. | 读取 EvaluationResult。"""

        document = self._get("result", resource_id, principal)
        result = EvaluationResult.model_validate_json(document) if document else None
        if result is not None and self.get_run(result.run_id, principal) is None:
            return None
        return result

    def get_gate(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> GateDecision | None:
        """Read a GateDecision. | 读取 GateDecision。"""

        document = self._get("gate", resource_id, principal)
        gate = GateDecision.model_validate_json(document) if document else None
        if gate is not None and self.get_run(gate.run_id, principal) is None:
            return None
        return gate

    def get_judge_profile(self, resource_id: UUID) -> JudgeProfile | None:
        """Read a JudgeProfile. | 读取 JudgeProfile。"""

        document = self._get("judge_profile", resource_id)
        return JudgeProfile.model_validate_json(document) if document else None

    def get_sample(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> SampleRecord | None:
        """Read a SampleRecord. | 读取 SampleRecord。"""

        document = self._get("sample", resource_id, principal)
        sample = SampleRecord.model_validate_json(document) if document else None
        if sample is not None and self.get_run(sample.run_id, principal) is None:
            return None
        return sample

    def get_annotation(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> HumanAnnotation | None:
        """Read a HumanAnnotation. | 读取 HumanAnnotation。"""

        document = self._get("annotation", resource_id, principal)
        annotation = HumanAnnotation.model_validate_json(document) if document else None
        if annotation is not None and self.get_run(annotation.run_id, principal) is None:
            return None
        return annotation

    def get_feedback_set(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> FeedbackSet | None:
        """Read a FeedbackSet. | 读取 FeedbackSet。"""

        document = self._get("feedback_set", resource_id, principal)
        feedback_set = FeedbackSet.model_validate_json(document) if document else None
        if feedback_set is not None and self.get_run(feedback_set.run_id, principal) is None:
            return None
        return feedback_set

    def get_feedback_handoff(
        self, resource_id: UUID, principal: WorkspaceServicePrincipal | None = None
    ) -> FeedbackHandoff | None:
        """Read a confirmed Catalyst handoff receipt. | 读取 Catalyst 交接回执。"""

        document = self._get("feedback_handoff", resource_id, principal)
        return FeedbackHandoff.model_validate_json(document) if document else None

    def save_feedback_handoff(
        self,
        feedback_set: FeedbackSet,
        handoff: FeedbackHandoff,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> None:
        """Atomically mark delivery and retain the target receipt. | 原子保存交接结果。"""

        documents = [
            (
                "feedback_set",
                str(feedback_set.id),
                feedback_set.model_dump_json(by_alias=True, exclude_none=True),
            ),
            (
                "feedback_handoff",
                str(handoff.id),
                handoff.model_dump_json(by_alias=True, exclude_none=True),
            ),
        ]
        organization_id = principal.organization_id if principal else None
        workspace_id = principal.workspace_id if principal else None
        scoped_documents = [(*row, organization_id, workspace_id) for row in documents]
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO resources("
                "kind, id, document, organization_id, workspace_id) VALUES (?, ?, ?, ?, ?)",
                scoped_documents,
            )

    def list_samples(
        self,
        run_id: UUID,
        *,
        only_passed: bool | None = None,
        only_annotated: bool | None = None,
        limit: int = 200,
        offset: int = 0,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> list[SampleRecord]:
        """List per-sample records for a run with optional filters. | 列出样本。"""

        if self.get_run(run_id, principal) is None:
            return []
        annotated_ids = self._annotation_sample_indexes(run_id, principal)
        rows = self._list_documents("sample", limit=limit, offset=offset, principal=principal)
        records: list[SampleRecord] = []
        for document in rows:
            sample = SampleRecord.model_validate_json(document)
            if sample.run_id != run_id:
                continue
            if only_passed is True and not sample.passed:
                continue
            if only_passed is False and sample.passed:
                continue
            if only_annotated is True and sample.sample_index not in annotated_ids:
                continue
            if only_annotated is False and sample.sample_index in annotated_ids:
                continue
            records.append(sample)
        return records

    def list_annotations(
        self,
        run_id: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> list[HumanAnnotation]:
        """List human annotations for a run. | 列出标注。"""

        if self.get_run(run_id, principal) is None:
            return []
        rows = self._list_documents("annotation", limit=1000, offset=0, principal=principal)
        annotations: list[HumanAnnotation] = []
        for document in rows:
            annotation = HumanAnnotation.model_validate_json(document)
            if annotation.run_id == run_id:
                annotations.append(annotation)
        return annotations

    def list_feedback_sets(
        self,
        run_id: UUID | None = None,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> list[FeedbackSet]:
        """List feedback sets, optionally for one run. | 列出反馈集。"""

        rows = self._list_documents("feedback_set", limit=1000, offset=0, principal=principal)
        sets: list[FeedbackSet] = []
        for document in rows:
            feedback_set = FeedbackSet.model_validate_json(document)
            if run_id is not None and feedback_set.run_id != run_id:
                continue
            if self.get_run(feedback_set.run_id, principal) is None:
                continue
            sets.append(feedback_set)
        return sets

    def _list_documents(
        self,
        kind: str,
        *,
        limit: int,
        offset: int,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> list[str]:
        with self._lock:
            if principal is None:
                cursor = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = ? "
                    "AND organization_id IS NULL AND workspace_id IS NULL LIMIT ? OFFSET ?",
                    (kind, limit, offset),
                )
            else:
                cursor = self._connection.execute(
                    "SELECT document FROM resources WHERE kind = ? AND organization_id = ? "
                    "AND workspace_id = ? LIMIT ? OFFSET ?",
                    (kind, principal.organization_id, principal.workspace_id, limit, offset),
                )
            return [str(row["document"]) for row in cursor.fetchall()]

    def _annotation_sample_indexes(
        self,
        run_id: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> set[int]:
        rows = self._list_documents("annotation", limit=10000, offset=0, principal=principal)
        indexes: set[int] = set()
        for document in rows:
            annotation = HumanAnnotation.model_validate_json(document)
            if annotation.run_id == run_id:
                indexes.add(annotation.sample_index)
        return indexes

    def resolve_idempotency(
        self,
        scope: str,
        key: str | None,
        digest: str,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> str | None:
        """Resolve replay or reject conflicting key reuse. | 解析幂等重放。"""

        if key is None:
            return None
        organization_id = principal.organization_id if principal else ""
        workspace_id = principal.workspace_id if principal else ""
        with self._lock:
            row = self._connection.execute(
                "SELECT request_hash, resource_id FROM idempotency WHERE scope = ? "
                "AND organization_id = ? AND workspace_id = ? AND key = ?",
                (scope, organization_id, workspace_id, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != digest:
            raise EchoError(
                code="ECHO_IDEMPOTENCY_CONFLICT",
                title="Idempotency key conflict",
                detail="The Idempotency-Key was already used with a different request body.",
                status=409,
            )
        return str(row["resource_id"])

    def remember_idempotency(
        self,
        *,
        scope: str,
        key: str | None,
        digest: str,
        resource_id: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> None:
        """Persist a command-to-resource mapping. | 持久化命令资源映射。"""

        if key is None:
            return
        organization_id = principal.organization_id if principal else ""
        workspace_id = principal.workspace_id if principal else ""
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO idempotency("
                "scope, organization_id, workspace_id, key, request_hash, resource_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (scope, organization_id, workspace_id, key, digest, str(resource_id)),
            )

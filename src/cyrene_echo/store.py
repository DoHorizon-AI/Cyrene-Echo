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
    FeedbackSet,
    GateDecision,
    HumanAnnotation,
    JudgeProfile,
    SampleRecord,
)
from cyrene_echo.errors import EchoError


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
                    PRIMARY KEY(kind, id)
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    PRIMARY KEY(scope, key)
                );
                CREATE INDEX IF NOT EXISTS idx_resources_kind_run
                    ON resources(kind, id);
                """
            )

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
        | EvaluationInput,
    ) -> None:
        """Upsert one typed resource document. | 写入一个类型化资源文档。"""

        resource_id = str(resource.id)
        document = resource.model_dump_json(by_alias=True, exclude_none=True)
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO resources(kind, id, document) VALUES (?, ?, ?)",
                (kind, resource_id, document),
            )

    def save_outcome(
        self, result: EvaluationResult, gate: GateDecision, run: EvaluationRun
    ) -> None:
        """Atomically commit result, gate, then terminal run. | 原子提交结果、门禁与运行。"""

        documents = [
            ("result", str(result.id), result.model_dump_json(by_alias=True, exclude_none=True)),
            ("gate", str(gate.id), gate.model_dump_json(by_alias=True, exclude_none=True)),
            ("run", str(run.id), run.model_dump_json(by_alias=True, exclude_none=True)),
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO resources(kind, id, document) VALUES (?, ?, ?)",
                documents,
            )

    def save_samples(self, samples: list[SampleRecord]) -> None:
        """Persist per-sample records for one run. | 持久化逐样本记录。"""

        if not samples:
            return
        rows = [
            ("sample", str(sample.id), sample.model_dump_json(by_alias=True, exclude_none=True))
            for sample in samples
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO resources(kind, id, document) VALUES (?, ?, ?)",
                rows,
            )

    def _get(self, kind: str, resource_id: UUID) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT document FROM resources WHERE kind = ? AND id = ?",
                (kind, str(resource_id)),
            ).fetchone()
        return str(row["document"]) if row else None

    def get_suite(self, resource_id: UUID) -> EvaluationSuite | None:
        """Read an EvaluationSuite. | 读取 EvaluationSuite。"""

        document = self._get("suite", resource_id)
        return EvaluationSuite.model_validate_json(document) if document else None

    def get_input(self, resource_id: UUID) -> EvaluationInput | None:
        """Read an evaluation preparation. | 读取评估准备资源。"""
        document = self._get("input", resource_id)
        return EvaluationInput.model_validate_json(document) if document else None

    def list_inputs(self) -> list[EvaluationInput]:
        """List drafts for independent discovery. | 列出可独立发现的草稿。"""
        with self._lock:
            rows = self._connection.execute(
                "SELECT document FROM resources WHERE kind = 'input' ORDER BY rowid DESC"
            ).fetchall()
        return [EvaluationInput.model_validate_json(row["document"]) for row in rows]

    def create_input(self, resource: EvaluationInput, key: str, digest: str) -> EvaluationInput:
        """Atomically persist an immutable input and its handoff receipt. | 原子保存输入。"""
        with self._lock, self._connection:
            replay = self.resolve_idempotency("import-input", key, digest)
            if replay is not None:
                existing = self.get_input(UUID(replay))
                if existing is None:
                    raise EchoError(
                        code="ECHO_INPUT_RECEIPT_INVALID",
                        title="Input receipt invalid",
                        detail="The persisted handoff receipt has no target resource.",
                        status=500,
                    )
                return existing
            self._connection.execute(
                "INSERT INTO resources(kind, id, document) VALUES ('input', ?, ?)",
                (str(resource.id), resource.model_dump_json(exclude_none=True)),
            )
            self._connection.execute(
                "INSERT INTO idempotency(scope, key, request_hash, resource_id) "
                "VALUES ('import-input', ?, ?, ?)",
                (key, digest, str(resource.id)),
            )
        return resource

    def get_run(self, resource_id: UUID) -> EvaluationRun | None:
        """Read an EvaluationRun. | 读取 EvaluationRun。"""

        document = self._get("run", resource_id)
        return EvaluationRun.model_validate_json(document) if document else None

    def get_result(self, resource_id: UUID) -> EvaluationResult | None:
        """Read an EvaluationResult. | 读取 EvaluationResult。"""

        document = self._get("result", resource_id)
        return EvaluationResult.model_validate_json(document) if document else None

    def get_gate(self, resource_id: UUID) -> GateDecision | None:
        """Read a GateDecision. | 读取 GateDecision。"""

        document = self._get("gate", resource_id)
        return GateDecision.model_validate_json(document) if document else None

    def get_judge_profile(self, resource_id: UUID) -> JudgeProfile | None:
        """Read a JudgeProfile. | 读取 JudgeProfile。"""

        document = self._get("judge_profile", resource_id)
        return JudgeProfile.model_validate_json(document) if document else None

    def get_sample(self, resource_id: UUID) -> SampleRecord | None:
        """Read a SampleRecord. | 读取 SampleRecord。"""

        document = self._get("sample", resource_id)
        return SampleRecord.model_validate_json(document) if document else None

    def get_annotation(self, resource_id: UUID) -> HumanAnnotation | None:
        """Read a HumanAnnotation. | 读取 HumanAnnotation。"""

        document = self._get("annotation", resource_id)
        return HumanAnnotation.model_validate_json(document) if document else None

    def get_feedback_set(self, resource_id: UUID) -> FeedbackSet | None:
        """Read a FeedbackSet. | 读取 FeedbackSet。"""

        document = self._get("feedback_set", resource_id)
        return FeedbackSet.model_validate_json(document) if document else None

    def list_samples(
        self,
        run_id: UUID,
        *,
        only_passed: bool | None = None,
        only_annotated: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SampleRecord]:
        """List per-sample records for a run with optional filters. | 列出样本。"""

        annotated_ids = self._annotation_sample_indexes(run_id)
        rows = self._list_documents("sample", limit=limit, offset=offset)
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

    def list_annotations(self, run_id: UUID) -> list[HumanAnnotation]:
        """List human annotations for a run. | 列出标注。"""

        rows = self._list_documents("annotation", limit=1000, offset=0)
        annotations: list[HumanAnnotation] = []
        for document in rows:
            annotation = HumanAnnotation.model_validate_json(document)
            if annotation.run_id == run_id:
                annotations.append(annotation)
        return annotations

    def list_feedback_sets(self, run_id: UUID | None = None) -> list[FeedbackSet]:
        """List feedback sets, optionally for one run. | 列出反馈集。"""

        rows = self._list_documents("feedback_set", limit=1000, offset=0)
        sets: list[FeedbackSet] = []
        for document in rows:
            feedback_set = FeedbackSet.model_validate_json(document)
            if run_id is not None and feedback_set.run_id != run_id:
                continue
            sets.append(feedback_set)
        return sets

    def _list_documents(self, kind: str, *, limit: int, offset: int) -> list[str]:
        with self._lock:
            cursor = self._connection.execute(
                "SELECT document FROM resources WHERE kind = ? LIMIT ? OFFSET ?",
                (kind, limit, offset),
            )
            return [str(row["document"]) for row in cursor.fetchall()]

    def _annotation_sample_indexes(self, run_id: UUID) -> set[int]:
        rows = self._list_documents("annotation", limit=10000, offset=0)
        indexes: set[int] = set()
        for document in rows:
            annotation = HumanAnnotation.model_validate_json(document)
            if annotation.run_id == run_id:
                indexes.add(annotation.sample_index)
        return indexes

    def resolve_idempotency(self, scope: str, key: str | None, digest: str) -> str | None:
        """Resolve replay or reject conflicting key reuse. | 解析幂等重放。"""

        if key is None:
            return None
        with self._lock:
            row = self._connection.execute(
                "SELECT request_hash, resource_id FROM idempotency WHERE scope = ? AND key = ?",
                (scope, key),
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
        self, *, scope: str, key: str | None, digest: str, resource_id: UUID
    ) -> None:
        """Persist a command-to-resource mapping. | 持久化命令资源映射。"""

        if key is None:
            return
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO idempotency(scope, key, request_hash, resource_id) "
                "VALUES (?, ?, ?, ?)",
                (scope, key, digest, str(resource_id)),
            )

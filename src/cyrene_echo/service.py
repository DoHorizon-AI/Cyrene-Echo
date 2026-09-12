"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 service.py                                                      │
│  Module: cyrene_echo.service                                        │
│  Role: Product lifecycle authority over evaluator measurements.      │
│                                                                     │
│  模块职责：基于评估器测量值管理产品运行、结果、门禁、逐样本、标注与反馈集。 │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from cyrene_echo.domain import (
    AnnotationPreference,
    ArtifactRef,
    ContractModel,
    CreateAnnotationRequest,
    CreateFeedbackSetRequest,
    CreateJudgeProfileRequest,
    CreateRunRequest,
    CreateSuiteRequest,
    EngineEvaluation,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    FeedbackHandoffStatus,
    FeedbackSet,
    FeedbackSetState,
    GateDecision,
    GateOutcome,
    HumanAnnotation,
    JudgeProfile,
    ProductFailure,
    RunState,
    SampleRecord,
    TrainingCandidateRow,
    utc_now,
)
from cyrene_echo.engine import (
    ArtifactPlane,
    EvaluationExecutionPort,
    ExchangeJudgePort,
    RunnerBinding,
    RunnerProfile,
    resolve_runner_binding,
)
from cyrene_echo.errors import EchoError, EvaluationEngineFailure
from cyrene_echo.store import EchoStore


def request_hash(command: ContractModel) -> str:
    """Hash a canonical request body for idempotency. | 生成幂等请求摘要。"""

    body = command.model_dump_json(by_alias=True, exclude_none=True)
    return hashlib.sha256(body.encode()).hexdigest()


class EchoService:
    """Own Echo resources while engines remain replaceable. | Echo 产品资源权威服务。"""

    def __init__(
        self,
        *,
        store: EchoStore,
        artifacts: ArtifactPlane,
        engine: EvaluationExecutionPort,
        judge_bearer_token: str | None = None,
    ) -> None:
        self.store = store
        self.artifacts = artifacts
        self.engine = engine
        self.judge_bearer_token = judge_bearer_token

    # ──────────────────────────────────────────────────────────────────
    # SECTION: EvaluationSuite + JudgeProfile lifecycle
    # ──────────────────────────────────────────────────────────────────

    def create_suite(
        self, command: CreateSuiteRequest, idempotency_key: str | None
    ) -> EvaluationSuite:
        """Create or replay an EvaluationSuite. | 创建或重放 EvaluationSuite。"""

        if command.evaluator == "llm_judge.v1" and command.judge_profile_id is None:
            raise EchoError(
                code="ECHO_SUITE_JUDGE_PROFILE_REQUIRED",
                title="Judge profile required",
                detail="An llm_judge.v1 suite must reference a JudgeProfile.",
                status=422,
            )
        if command.judge_profile_id is not None:
            profile = self.store.get_judge_profile(command.judge_profile_id)
            if profile is None:
                raise EchoError(
                    code="ECHO_JUDGE_PROFILE_NOT_FOUND",
                    title="Judge profile not found",
                    detail="The referenced JudgeProfile does not exist.",
                    status=404,
                )
        digest = request_hash(command)
        replay_id = self.store.resolve_idempotency("create-suite", idempotency_key, digest)
        if replay_id is not None:
            return self.get_suite(UUID(replay_id))
        now = utc_now()
        suite = EvaluationSuite(
            id=uuid4(),
            name=command.name,
            evaluator=command.evaluator,
            expected_field=command.expected_field,
            actual_field=command.actual_field,
            threshold=command.threshold,
            judge_profile_id=command.judge_profile_id,
            created_at=now,
            updated_at=now,
            resource_version=1,
        )
        self.store.save("suite", suite)
        self.store.remember_idempotency(
            scope="create-suite",
            key=idempotency_key,
            digest=digest,
            resource_id=suite.id,
        )
        return suite

    def get_suite(self, suite_id: UUID) -> EvaluationSuite:
        """Read an EvaluationSuite. | 读取 EvaluationSuite。"""

        suite = self.store.get_suite(suite_id)
        if suite is None:
            raise EchoError(
                code="ECHO_SUITE_NOT_FOUND",
                title="EvaluationSuite not found",
                detail="No EvaluationSuite exists with the requested id.",
                status=404,
            )
        return suite

    def create_judge_profile(
        self, command: CreateJudgeProfileRequest, idempotency_key: str | None
    ) -> JudgeProfile:
        """Create or replay a JudgeProfile. | 创建或重放 JudgeProfile。"""

        digest = request_hash(command)
        replay_id = self.store.resolve_idempotency("create-judge-profile", idempotency_key, digest)
        if replay_id is not None:
            profile = self.store.get_judge_profile(UUID(replay_id))
            assert profile is not None
            return profile
        now = utc_now()
        profile = JudgeProfile(
            id=uuid4(),
            name=command.name,
            judge_model=command.judge_model,
            exchange_endpoint_ref=command.exchange_endpoint_ref,
            prompt_template=command.prompt_template,
            created_at=now,
            updated_at=now,
            resource_version=1,
        )
        self.store.save("judge_profile", profile)
        self.store.remember_idempotency(
            scope="create-judge-profile",
            key=idempotency_key,
            digest=digest,
            resource_id=profile.id,
        )
        return profile

    def get_judge_profile(self, profile_id: UUID) -> JudgeProfile:
        """Read a JudgeProfile. | 读取 JudgeProfile。"""

        profile = self.store.get_judge_profile(profile_id)
        if profile is None:
            raise EchoError(
                code="ECHO_JUDGE_PROFILE_NOT_FOUND",
                title="Judge profile not found",
                detail="No JudgeProfile exists with the requested id.",
                status=404,
            )
        return profile

    # ──────────────────────────────────────────────────────────────────
    # SECTION: Session import + EvaluationRun execution
    # ──────────────────────────────────────────────────────────────────

    def import_sessions(self, payload: bytes) -> ArtifactRef:
        """Publish raw session JSONL bytes as an immutable dataset artifact. | 导入会话。"""

        return self.artifacts.publish_bytes(payload, kind="dataset")

    def create_run(self, command: CreateRunRequest, idempotency_key: str | None) -> EvaluationRun:
        """Execute an evaluator and atomically publish result, gate, samples. | 执行评估。"""

        suite = self.get_suite(command.suite_id)
        binding = self._binding_for(command.engine_binding_id, suite)
        digest = request_hash(command)
        replay_id = self.store.resolve_idempotency("create-run", idempotency_key, digest)
        if replay_id is not None:
            return self.get_run(UUID(replay_id))
        now = utc_now()
        run = EvaluationRun(
            id=uuid4(),
            suite_id=suite.id,
            state=RunState.RUNNING,
            input_artifact=command.input_artifact,
            engine_binding_id=command.engine_binding_id,
            created_at=now,
            updated_at=now,
            resource_version=1,
        )
        self.store.save("run", run)
        self.store.remember_idempotency(
            scope="create-run",
            key=idempotency_key,
            digest=digest,
            resource_id=run.id,
        )
        report_path = self.artifacts.stage_path(f"{run.id}.json")
        try:
            source_path = self.artifacts.resolve(command.input_artifact)
            engine = self._engine_for(binding, suite)
            measurement = engine.evaluate(source_path, suite, report_path)
            report = self.artifacts.publish(report_path)
        except (EchoError, EvaluationEngineFailure) as exc:
            error = self._as_evaluation_error(exc, run.id)
            failed = run.model_copy(
                update={
                    "state": RunState.FAILED,
                    "failure": ProductFailure(
                        code=error.code,
                        message=error.detail,
                        retryable=error.retryable,
                    ),
                    "updated_at": utc_now(),
                    "resource_version": 2,
                }
            )
            self.store.save("run", failed)
            raise error from exc
        finally:
            report_path.unlink(missing_ok=True)

        completed_at = utc_now()
        result = EvaluationResult(
            id=uuid4(),
            run_id=run.id,
            score=measurement.score,
            metrics=self._metrics_for(suite.evaluator, measurement),
            record_count=measurement.record_count,
            passed_count=measurement.passed_count,
            report_artifact=report,
            input_digest=command.input_artifact.digest,
            created_at=completed_at,
            resource_version=1,
        )
        gate = GateDecision(
            id=uuid4(),
            run_id=run.id,
            result_id=result.id,
            outcome=(GateOutcome.PASS if result.score >= suite.threshold else GateOutcome.FAIL),
            observed_score=result.score,
            threshold=suite.threshold,
            created_at=completed_at,
            resource_version=1,
        )
        samples = self._persist_samples(run.id, suite, command.input_artifact.digest, measurement)
        succeeded = run.model_copy(
            update={
                "state": RunState.SUCCEEDED,
                "result_id": result.id,
                "gate_id": gate.id,
                "updated_at": completed_at,
                "resource_version": 2,
            }
        )
        self.store.save_outcome(result, gate, succeeded)
        self.store.save_samples(samples)
        return succeeded

    def _binding_for(self, binding_id: str, suite: EvaluationSuite) -> RunnerBinding:
        """Resolve the declared runner binding and reject evaluator mismatches. | 校验绑定。"""

        binding = resolve_runner_binding(binding_id)
        if binding.evaluator != suite.evaluator:
            raise EchoError(
                code="ECHO_RUNNER_BINDING_MISMATCH",
                title="Runner binding mismatch",
                detail=(
                    f"Binding '{binding.binding_id}' is declared for '{binding.evaluator}' "
                    f"suites and cannot execute a '{suite.evaluator}' suite."
                ),
                status=422,
            )
        return binding

    def _engine_for(
        self, binding: RunnerBinding, suite: EvaluationSuite
    ) -> EvaluationExecutionPort:
        """Select the runner declared by the binding; fail closed if unavailable. | 选引擎。"""

        if binding.profile == RunnerProfile.DIRECT_PLUGIN:
            return self.engine
        if suite.judge_profile_id is None:
            raise EchoError(
                code="ECHO_SUITE_JUDGE_PROFILE_REQUIRED",
                title="Judge profile required",
                detail="An llm_judge.v1 suite must reference a JudgeProfile.",
                status=422,
            )
        if not self.judge_bearer_token:
            raise EchoError(
                code="ECHO_JUDGE_CREDENTIAL_UNAVAILABLE",
                title="Judge credential unavailable",
                detail=(
                    "Exchange judge bearer token is not configured; live judge is WIRED_NOT_RUN."
                ),
                status=503,
                retryable=True,
            )
        profile = self.get_judge_profile(suite.judge_profile_id)
        return ExchangeJudgePort(profile, bearer_token=self.judge_bearer_token)

    def _persist_samples(
        self,
        run_id: UUID,
        suite: EvaluationSuite,
        input_digest: str,
        measurement: EngineEvaluation,
    ) -> list[SampleRecord]:
        """Persist immutable per-sample evidence anchored to the run. | 持久化样本。"""

        now = utc_now()
        records: list[SampleRecord] = []
        for sample in measurement.samples:
            records.append(
                SampleRecord(
                    id=uuid4(),
                    run_id=run_id,
                    sample_index=sample.sample_index,
                    evaluator=suite.evaluator,
                    input_digest=input_digest,
                    input_record=sample.input_record,
                    expected=sample.expected,
                    actual=sample.actual,
                    raw_output=sample.raw_output,
                    passed=sample.passed,
                    score=sample.score,
                    model_ref=sample.model_ref,
                    endpoint_ref=sample.endpoint_ref,
                    usage=sample.usage,
                    judge_identity=sample.judge_identity,
                    created_at=now,
                    resource_version=1,
                )
            )
        return records

    @staticmethod
    def _metrics_for(evaluator: str, measurement: EngineEvaluation) -> dict[str, float]:
        """Assemble stable metric names for a result. | 汇总指标。"""

        metrics: dict[str, float] = {"score": measurement.score}
        if evaluator == "exact_match.v1":
            metrics["exactMatch"] = measurement.score
        if evaluator == "llm_judge.v1":
            metrics["judgeScore"] = measurement.score
        return metrics

    def get_run(self, run_id: UUID) -> EvaluationRun:
        """Read an EvaluationRun including persisted failures. | 读取评估运行。"""

        run = self.store.get_run(run_id)
        if run is None:
            raise EchoError(
                code="ECHO_RUN_NOT_FOUND",
                title="EvaluationRun not found",
                detail="No EvaluationRun exists with the requested id.",
                status=404,
            )
        return run

    def get_result(self, result_id: UUID) -> EvaluationResult:
        """Read an immutable EvaluationResult. | 读取不可变评估结果。"""

        result = self.store.get_result(result_id)
        if result is None:
            raise EchoError(
                code="ECHO_RESULT_NOT_FOUND",
                title="EvaluationResult not found",
                detail="No EvaluationResult exists with the requested id.",
                status=404,
            )
        return result

    def get_gate(self, gate_id: UUID) -> GateDecision:
        """Read an immutable GateDecision. | 读取不可变门禁决策。"""

        gate = self.store.get_gate(gate_id)
        if gate is None:
            raise EchoError(
                code="ECHO_GATE_NOT_FOUND",
                title="GateDecision not found",
                detail="No GateDecision exists with the requested id.",
                status=404,
            )
        return gate

    # ──────────────────────────────────────────────────────────────────
    # SECTION: Per-sample review, human annotation, filtering
    # ──────────────────────────────────────────────────────────────────

    def list_samples(
        self,
        run_id: UUID,
        *,
        only_passed: bool | None = None,
        only_annotated: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SampleRecord]:
        """List per-sample records with optional filters. | 列出样本。"""

        self._require_run(run_id)
        return self.store.list_samples(
            run_id,
            only_passed=only_passed,
            only_annotated=only_annotated,
            limit=limit,
            offset=offset,
        )

    def get_sample(self, run_id: UUID, sample_index: int) -> SampleRecord:
        """Read one per-sample record with its annotation context. | 读取单个样本。"""

        self._require_run(run_id)
        samples = self.store.list_samples(run_id, limit=10000, offset=0)
        for sample in samples:
            if sample.sample_index == sample_index:
                return sample
        raise EchoError(
            code="ECHO_SAMPLE_NOT_FOUND",
            title="Sample not found",
            detail="No SampleRecord exists with the requested index in this run.",
            status=404,
            resource_ref=f"/api/v1/evaluation-runs/{run_id}/samples/{sample_index}",
        )

    def annotate_sample(self, run_id: UUID, command: CreateAnnotationRequest) -> HumanAnnotation:
        """Create or update a human annotation (idempotent per sample+reviewer). | 标注样本。"""

        self._require_run(run_id)
        self.get_sample(run_id, command.sample_index)
        existing = self._find_annotation(run_id, command.sample_index, command.reviewer)
        now = utc_now()
        if existing is not None:
            updated = existing.model_copy(
                update={
                    "manual_score": command.manual_score,
                    "corrected_output": command.corrected_output,
                    "preference": command.preference,
                    "note": command.note,
                    "updated_at": now,
                    "resource_version": existing.resource_version + 1,
                }
            )
            self.store.save("annotation", updated)
            return updated
        annotation = HumanAnnotation(
            id=uuid4(),
            run_id=run_id,
            sample_index=command.sample_index,
            reviewer=command.reviewer,
            manual_score=command.manual_score,
            corrected_output=command.corrected_output,
            preference=command.preference,
            note=command.note,
            created_at=now,
            updated_at=now,
            resource_version=1,
        )
        self.store.save("annotation", annotation)
        return annotation

    def list_annotations(self, run_id: UUID) -> list[HumanAnnotation]:
        """List human annotations for a run. | 列出标注。"""

        self._require_run(run_id)
        return self.store.list_annotations(run_id)

    def _find_annotation(
        self, run_id: UUID, sample_index: int, reviewer: str
    ) -> HumanAnnotation | None:
        for annotation in self.store.list_annotations(run_id):
            if annotation.sample_index == sample_index and annotation.reviewer == reviewer:
                return annotation
        return None

    def _require_run(self, run_id: UUID) -> None:
        if self.store.get_run(run_id) is None:
            raise EchoError(
                code="ECHO_RUN_NOT_FOUND",
                title="EvaluationRun not found",
                detail="No EvaluationRun exists with the requested id.",
                status=404,
            )

    # ──────────────────────────────────────────────────────────────────
    # SECTION: FeedbackSet + Catalyst-compatible export
    # ──────────────────────────────────────────────────────────────────

    def create_feedback_set(
        self, command: CreateFeedbackSetRequest, idempotency_key: str | None
    ) -> FeedbackSet:
        """Build a feedback set from explicitly user-selected samples only. | 创建反馈集。"""

        self._require_run(command.run_id)
        samples = self.store.list_samples(command.run_id, limit=10000, offset=0)
        indexes = {sample.sample_index for sample in samples}
        unknown = [idx for idx in command.sample_indexes if idx not in indexes]
        if unknown:
            raise EchoError(
                code="ECHO_FEEDBACK_SAMPLE_UNKNOWN",
                title="Feedback sample unknown",
                detail="One or more selected sample indexes do not belong to this run.",
                status=422,
                resource_ref=f"/api/v1/evaluation-runs/{command.run_id}/samples",
            )
        annotations = self.store.list_annotations(command.run_id)
        annotation_map = {annotation.sample_index: annotation for annotation in annotations}
        orphan = [
            aid
            for aid in command.annotation_ids
            if aid not in {annotation.id for annotation in annotations}
        ]
        if orphan:
            raise EchoError(
                code="ECHO_ANNOTATION_UNKNOWN",
                title="Annotation unknown",
                detail="One or more annotation ids do not belong to this run.",
                status=422,
            )
        for annotation_id in command.annotation_ids:
            sample_index = next(
                annotation.sample_index
                for annotation in annotations
                if annotation.id == annotation_id
            )
            if sample_index not in command.sample_indexes:
                raise EchoError(
                    code="ECHO_ANNOTATION_NOT_SELECTED",
                    title="Annotation not selected",
                    detail="A referenced annotation belongs to a sample that was not selected.",
                    status=422,
                )
        digest = request_hash(command)
        replay_id = self.store.resolve_idempotency("create-feedback-set", idempotency_key, digest)
        if replay_id is not None:
            existing = self.store.get_feedback_set(UUID(replay_id))
            assert existing is not None
            return existing
        now = utc_now()
        candidate_count = self._count_candidates(
            command.sample_indexes, annotation_map, samples, command.run_id, command.annotation_ids
        )
        feedback_set = FeedbackSet(
            id=uuid4(),
            name=command.name,
            run_id=command.run_id,
            sample_indexes=sorted(set(command.sample_indexes)),
            annotation_ids=list(command.annotation_ids),
            state=FeedbackSetState.OPEN,
            export_artifact=None,
            handoff_status=FeedbackHandoffStatus.PREPARED,
            candidate_count=candidate_count,
            created_at=now,
            updated_at=now,
            resource_version=1,
        )
        self.store.save("feedback_set", feedback_set)
        self.store.remember_idempotency(
            scope="create-feedback-set",
            key=idempotency_key,
            digest=digest,
            resource_id=feedback_set.id,
        )
        return feedback_set

    def get_feedback_set(self, feedback_set_id: UUID) -> FeedbackSet:
        """Read a FeedbackSet. | 读取 FeedbackSet。"""

        feedback_set = self.store.get_feedback_set(feedback_set_id)
        if feedback_set is None:
            raise EchoError(
                code="ECHO_FEEDBACK_SET_NOT_FOUND",
                title="FeedbackSet not found",
                detail="No FeedbackSet exists with the requested id.",
                status=404,
            )
        return feedback_set

    def list_feedback_sets(self, run_id: UUID | None = None) -> list[FeedbackSet]:
        """List feedback sets, optionally for one run. | 列出反馈集。"""

        return self.store.list_feedback_sets(run_id)

    def export_feedback_set(self, feedback_set_id: UUID) -> tuple[FeedbackSet, bytes]:
        """Export a feedback set as Catalyst-compatible JSONL; never auto-deliver. | 导出。"""

        feedback_set = self.get_feedback_set(feedback_set_id)
        if feedback_set.export_artifact is not None:
            # A selected export is immutable; later annotations need a new FeedbackSet.
            return feedback_set, self.artifacts.resolve(feedback_set.export_artifact).read_bytes()
        run = self.get_run(feedback_set.run_id)
        suite = self.get_suite(run.suite_id)
        samples = self.store.list_samples(feedback_set.run_id, limit=10000, offset=0)
        sample_map = {sample.sample_index: sample for sample in samples}
        annotations = self.store.list_annotations(feedback_set.run_id)
        annotation_map = {
            annotation.sample_index: annotation
            for annotation in annotations
            if not feedback_set.annotation_ids or annotation.id in feedback_set.annotation_ids
        }
        rows: list[TrainingCandidateRow] = []
        for sample_index in feedback_set.sample_indexes:
            sample = sample_map.get(sample_index)
            if sample is None:
                continue
            annotation = annotation_map.get(sample_index)
            rows.append(self._candidate_row(sample, suite, annotation))
        payload = (
            "\n".join(row.model_dump_json(by_alias=True, exclude_none=True) for row in rows)
            + ("\n" if rows else "")
        ).encode("utf-8")
        artifact = self.artifacts.publish_bytes(payload, kind="dataset")
        now = utc_now()
        exported = feedback_set.model_copy(
            update={
                "state": FeedbackSetState.EXPORTED,
                "export_artifact": artifact,
                "candidate_count": len(rows),
                "updated_at": now,
                "resource_version": feedback_set.resource_version + 1,
            }
        )
        self.store.save("feedback_set", exported)
        return exported, payload

    def _candidate_row(
        self,
        sample: SampleRecord,
        suite: EvaluationSuite,
        annotation: HumanAnnotation | None,
    ) -> TrainingCandidateRow:
        """Project one sample into a Catalyst-compatible training candidate. | 生成训练候选。"""

        instruction = self._text_or(
            sample.input_record.get("instruction"),
            sample.input_record.get(suite.expected_field),
        )
        expected = self._text_or(sample.input_record.get(suite.expected_field), sample.expected)
        corrected = annotation.corrected_output if annotation is not None else None
        preference = annotation.preference if annotation is not None else None
        annotated_by = annotation.reviewer if annotation is not None else None
        source_kind: Literal["low_score", "human_corrected", "preference"]
        rejected: str | None
        if preference == AnnotationPreference.PREFER_CORRECTED and corrected:
            source_kind = "preference"
            output = corrected
            rejected = self._text_or(sample.raw_output, sample.actual)
        elif corrected:
            source_kind = "human_corrected"
            output = corrected
            rejected = None
        elif not sample.passed:
            source_kind = "low_score"
            output = expected
            rejected = None
        else:
            source_kind = "low_score"
            output = expected
            rejected = None
        return TrainingCandidateRow(
            instruction=instruction,
            output=output,
            input=self._text_or(sample.input_record.get("input"), ""),
            rejected_output=rejected,
            source_run_id=str(sample.run_id),
            source_sample_index=sample.sample_index,
            source_kind=source_kind,
            evaluator=sample.evaluator,
            model_ref=sample.model_ref,
            annotated_by=annotated_by,
            original_sample=sample.input_record,
            model_output=sample.raw_output or self._text_or(sample.actual),
            evaluation_score=sample.score,
            human_annotation=annotation.model_dump(mode="json", exclude_none=True)
            if annotation is not None
            else None,
        )

    @staticmethod
    def _text_or(*candidates: object) -> str:
        """Return the first non-empty text projection; never falsify. | 投影文本。"""

        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, str | int | float | bool):
                text = str(candidate)
            else:
                text = json.dumps(candidate, sort_keys=True, ensure_ascii=False)
            if text:
                return text
        return ""

    def _count_candidates(
        self,
        sample_indexes: list[int],
        annotation_map: dict[int, HumanAnnotation],
        samples: list[SampleRecord],
        run_id: UUID,
        annotation_ids: list[UUID],
    ) -> int:
        """Count training candidates that will be produced on export. | 统计候选数。"""

        del annotation_ids, run_id
        sample_map = {sample.sample_index: sample for sample in samples}
        return sum(1 for idx in sample_indexes if idx in sample_map)

    @staticmethod
    def _as_evaluation_error(exc: EchoError | EvaluationEngineFailure, run_id: UUID) -> EchoError:
        resource_ref = f"/api/v1/evaluation-runs/{run_id}"
        if isinstance(exc, EchoError):
            return EchoError(
                code=exc.code,
                title=exc.title,
                detail=exc.detail,
                status=exc.status,
                retryable=exc.retryable,
                resource_ref=resource_ref,
            )
        return EchoError(
            code="ECHO_EVALUATION_FAILED",
            title="Evaluation failed",
            detail=str(exc),
            status=422,
            resource_ref=resource_ref,
        )

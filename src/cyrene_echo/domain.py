"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 domain.py                                                       │
│  Module: cyrene_echo.domain                                         │
│  Role: Product-owned evaluation and gate boundary models.           │
│                                                                     │
│  模块职责：定义评估运行、结果与门禁决策的稳定产品契约。                     │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def utc_now() -> datetime:
    """Return a timezone-aware timestamp. | 返回带时区时间。"""

    return datetime.now(UTC)


class ContractModel(BaseModel):
    """Stable camelCase wire model. | 稳定 camelCase 线格式模型。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class SuiteState(StrEnum):
    """EvaluationSuite lifecycle. | 评估套件生命周期。"""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class RunState(StrEnum):
    """EvaluationRun Product lifecycle. | 评估运行产品生命周期。"""

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GateOutcome(StrEnum):
    """Immutable gate policy outcome. | 不可变门禁结果。"""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class FeedbackSetState(StrEnum):
    """FeedbackSet lifecycle. | 反馈集生命周期。"""

    OPEN = "OPEN"
    EXPORTED = "EXPORTED"


class FeedbackHandoffStatus(StrEnum):
    """Honest Catalyst handoff status; never fakes delivery. | 真实交接状态。"""

    PREPARED = "PREPARED"
    HANDLED_OFF = "HANDLED_OFF"


class AnnotationPreference(StrEnum):
    """Explicit human preference over one sample. | 人工偏好标记。"""

    ACCEPT = "accept"
    REJECT = "reject"
    PREFER_CORRECTED = "prefer_corrected"


class ArtifactRef(ContractModel):
    """Product projection of the canonical provider-neutral ArtifactRef. | 制品引用投影。"""

    model_config = ConfigDict(
        alias_generator=None,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )

    uri: str = Field(pattern=r"^artifact://sha256/[0-9a-f]{64}$")
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    kind: str = Field(
        min_length=1,
        max_length=128,
        description="Opaque producer-owned category; Platform does not define its vocabulary.",
    )
    manifest_digest: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )


class ProductFailure(ContractModel):
    """Failure persisted on a Product resource. | 产品资源持久化失败。"""

    code: str
    message: str
    retryable: bool


class EvaluationSuite(ContractModel):
    """Reusable evaluation and gate policy. | 可复用评估及门禁策略。"""

    id: UUID
    name: str = Field(min_length=1, max_length=200)
    evaluator: Literal["exact_match.v1", "llm_judge.v1"] = "exact_match.v1"
    expected_field: str = Field(min_length=1, max_length=200)
    actual_field: str = Field(min_length=1, max_length=200)
    threshold: float = Field(ge=0, le=1)
    judge_profile_id: UUID | None = None
    state: SuiteState = SuiteState.ACTIVE
    created_at: datetime
    updated_at: datetime
    resource_version: int = Field(ge=1)


class EvaluationRun(ContractModel):
    """Product execution record, distinct from engine execution. | 产品运行记录。"""

    id: UUID
    suite_id: UUID
    state: RunState
    input_artifact: ArtifactRef
    engine_binding_id: str = Field(min_length=1, max_length=200)
    result_id: UUID | None = None
    gate_id: UUID | None = None
    failure: ProductFailure | None = None
    created_at: datetime
    updated_at: datetime
    resource_version: int = Field(ge=1)


class EvaluationResult(ContractModel):
    """Immutable evaluation measurements and report reference. | 不可变评估结果。"""

    id: UUID
    run_id: UUID
    score: float = Field(ge=0, le=1)
    metrics: dict[str, float]
    record_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    report_artifact: ArtifactRef
    input_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime
    resource_version: int = Field(ge=1)


class GateDecision(ContractModel):
    """Immutable Product policy decision over a result. | 产品门禁策略决策。"""

    id: UUID
    run_id: UUID
    result_id: UUID
    outcome: GateOutcome
    rule: Literal["score >= threshold"] = "score >= threshold"
    observed_score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    created_at: datetime
    resource_version: int = Field(ge=1)


class CreateSuiteRequest(ContractModel):
    """Create-suite command. | 创建评估套件请求。"""

    name: str = Field(min_length=1, max_length=200)
    evaluator: Literal["exact_match.v1", "llm_judge.v1"] = "exact_match.v1"
    expected_field: str = Field(min_length=1, max_length=200)
    actual_field: str = Field(min_length=1, max_length=200)
    threshold: float = Field(ge=0, le=1)
    judge_profile_id: UUID | None = None


class CreateRunRequest(ContractModel):
    """Create-run command. | 创建评估运行请求。"""

    suite_id: UUID
    input_artifact: ArtifactRef
    engine_binding_id: str = Field(min_length=1, max_length=200)


class EngineEvaluation(ContractModel):
    """Measurements returned by an engine before Product commit. | 引擎测量结果。"""

    record_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    score: float = Field(ge=0, le=1)
    samples: list[SampleEvaluation] = Field(default_factory=list)


class ProblemDetails(ContractModel):
    """RFC 9457 response with stable Echo extensions. | RFC 9457 错误响应。"""

    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    instance: str
    code: str
    retryable: bool
    trace_id: str
    resource_ref: str | None = None


class UsageFacts(ContractModel):
    """Provider-reported token usage; never estimated when missing. | 真实 usage。"""

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    source: str = Field(default="provider", min_length=1, max_length=100)


class JudgeProfile(ContractModel):
    """Reusable LLM-judge configuration resolved through Exchange. | 判官配置。"""

    id: UUID
    name: str = Field(min_length=1, max_length=200)
    judge_model: str = Field(min_length=1, max_length=200)
    exchange_endpoint_ref: str = Field(min_length=1, max_length=500)
    prompt_template: str = Field(min_length=1, max_length=4000)
    created_at: datetime
    updated_at: datetime
    resource_version: int = Field(ge=1)


class CreateJudgeProfileRequest(ContractModel):
    """Create-judge-profile command. | 创建判官配置请求。"""

    name: str = Field(min_length=1, max_length=200)
    judge_model: str = Field(min_length=1, max_length=200)
    exchange_endpoint_ref: str = Field(min_length=1, max_length=500)
    prompt_template: str = Field(min_length=1, max_length=4000)


class SampleEvaluation(ContractModel):
    """Per-sample measurement returned by an engine before Product commit. | 逐样本测量。"""

    sample_index: int = Field(ge=1)
    input_record: dict[str, Any]
    expected: Any | None = None
    actual: Any | None = None
    raw_output: str | None = None
    passed: bool
    score: float = Field(ge=0, le=1)
    model_ref: str | None = Field(default=None, max_length=200)
    endpoint_ref: str | None = Field(default=None, max_length=500)
    usage: UsageFacts | None = None
    judge_identity: str | None = Field(default=None, max_length=300)


class SampleRecord(ContractModel):
    """Immutable per-sample evaluation evidence. | 不可变逐样本评估证据。"""

    id: UUID
    run_id: UUID
    sample_index: int = Field(ge=1)
    evaluator: str = Field(min_length=1, max_length=100)
    input_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    input_record: dict[str, Any]
    expected: Any | None = None
    actual: Any | None = None
    raw_output: str | None = None
    passed: bool
    score: float = Field(ge=0, le=1)
    model_ref: str | None = Field(default=None, max_length=200)
    endpoint_ref: str | None = Field(default=None, max_length=500)
    usage: UsageFacts | None = None
    judge_identity: str | None = Field(default=None, max_length=300)
    created_at: datetime
    resource_version: int = Field(ge=1)


class HumanAnnotation(ContractModel):
    """Explicit human review over one sample. | 人工标注。"""

    id: UUID
    run_id: UUID
    sample_index: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=200)
    manual_score: float | None = Field(default=None, ge=0, le=1)
    corrected_output: str | None = Field(default=None, max_length=10000)
    preference: AnnotationPreference | None = None
    note: str = Field(default="", max_length=2000)
    created_at: datetime
    updated_at: datetime
    resource_version: int = Field(ge=1)


class CreateAnnotationRequest(ContractModel):
    """Create or update a human annotation. | 创建或更新人工标注。"""

    sample_index: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=200)
    manual_score: float | None = Field(default=None, ge=0, le=1)
    corrected_output: str | None = Field(default=None, max_length=10000)
    preference: AnnotationPreference | None = None
    note: str = Field(default="", max_length=2000)


class FeedbackSet(ContractModel):
    """User-selected training candidates anchored to one run. | 用户显式选择的训练候选集。"""

    id: UUID
    name: str = Field(min_length=1, max_length=200)
    run_id: UUID
    sample_indexes: list[int] = Field(default_factory=list)
    annotation_ids: list[UUID] = Field(default_factory=list)
    state: FeedbackSetState = FeedbackSetState.OPEN
    export_artifact: ArtifactRef | None = None
    handoff_status: FeedbackHandoffStatus = FeedbackHandoffStatus.PREPARED
    candidate_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    resource_version: int = Field(ge=1)


class CreateFeedbackSetRequest(ContractModel):
    """Create-feedback-set command; samples are explicitly selected. | 创建反馈集。"""

    name: str = Field(min_length=1, max_length=200)
    run_id: UUID
    sample_indexes: list[int] = Field(min_length=1)
    annotation_ids: list[UUID] = Field(default_factory=list)


class ExportFeedbackSetResponse(ContractModel):
    """Export outcome; handoff is PREPARED, never faked. | 导出结果。"""

    feedback_set: FeedbackSet
    export_artifact: ArtifactRef
    candidate_count: int = Field(ge=0)
    handoff_status: FeedbackHandoffStatus = FeedbackHandoffStatus.PREPARED


class TrainingCandidateRow(ContractModel):
    """Catalyst-compatible training candidate with provenance. | 训练候选行。"""

    instruction: str = Field(min_length=1)
    output: str = Field(min_length=1)
    input: str = ""
    rejected_output: str | None = None
    source_run_id: str
    source_sample_index: int = Field(ge=1)
    source_kind: Literal["low_score", "human_corrected", "preference"]
    evaluator: str
    model_ref: str | None = None
    annotated_by: str | None = None
    original_sample: dict[str, Any] = Field(default_factory=dict)
    model_output: str | None = None
    evaluation_score: float | None = None
    human_annotation: dict[str, Any] | None = None


class ProductResourceRef(ContractModel):
    """Product identity without imported business authority. | 外部产品资源身份。"""

    uri: str = Field(pattern=r"^(cyrene|https?)://[^\s]+$", max_length=2000)
    id: str = Field(min_length=1, max_length=512)
    resource_version: int = Field(ge=1)


class ImportEvaluationInput(ContractModel):
    """Immutable source snapshot for a future evaluation. | 待评估的不可变快照。"""

    source_ref: ProductResourceRef
    artifact: ArtifactRef
    format: Literal["NAVIGATOR_TEXT_JSONL_V1"]
    content_refs: list[str] = Field(min_length=1, max_length=2000)
    provenance_refs: list[str] = Field(default_factory=list, max_length=100)


class EvaluationInput(ImportEvaluationInput):
    """A draft never invokes an evaluator. | 草稿不会调用评估器。"""

    id: UUID
    resource_ref: ProductResourceRef
    state: Literal["DRAFT", "STARTED"] = "DRAFT"
    evaluation_run: ProductResourceRef | None = None
    created_at: datetime

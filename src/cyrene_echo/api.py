"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 api.py                                                          │
│  Module: cyrene_echo.api                                            │
│  Role: Versioned HTTP adapter for the Echo Product contract.         │
│                                                                     │
│  模块职责：Echo 产品契约的版本化 HTTP 适配器（含会话反馈与最小界面）。    │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi import Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response

from cyrene_echo.domain import (
    ArtifactRef,
    CreateAnnotationRequest,
    CreateFeedbackSetRequest,
    CreateJudgeProfileRequest,
    CreateRunRequest,
    CreateSuiteRequest,
    EvaluationInput,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    ExportFeedbackSetResponse,
    FeedbackSet,
    GateDecision,
    HumanAnnotation,
    ImportEvaluationInput,
    JudgeProfile,
    ProblemDetails,
    SampleRecord,
)
from cyrene_echo.engine import EchoArtifactPlane, EvaluationExecutionPort
from cyrene_echo.errors import EchoError, EvaluationEngineFailure, map_echo_error
from cyrene_echo.lifecycle import (
    EvaluateInput,
    HandoffReceipt,
    LifecycleActions,
    SendFeedback,
)
from cyrene_echo.logging import (
    emit_diagnostic_error,
    parse_w3c_traceparent,
    sanitize_request_id,
)
from cyrene_echo.plugin_evaluation import evaluation_port_from_environment
from cyrene_echo.service import EchoService
from cyrene_echo.store import EchoStore
from cyrene_echo.ui_page import INDEX_HTML


def create_app(
    *,
    database_path: Path,
    artifact_root: Path,
    engine: EvaluationExecutionPort | None = None,
    judge_bearer_token: str | None = None,
    catalyst_url: str | None = None,
) -> FastAPI:
    """Build Echo with explicit persistence and evaluator adapters. | 创建 Echo 应用。"""

    store = EchoStore(database_path)
    service = EchoService(
        store=store,
        artifacts=EchoArtifactPlane(artifact_root),
        engine=engine or evaluation_port_from_environment(),
        judge_bearer_token=judge_bearer_token,
    )
    app = FastAPI(title="Cyrene Echo Product API", version="1.0.0")
    app.state.echo_store = store
    app.state.echo_service = service
    lifecycle = LifecycleActions(service, catalyst_url)
    app.state.echo_lifecycle = lifecycle

    @app.post(
        "/api/v1/evaluation-inputs",
        response_model=EvaluationInput,
        status_code=201,
        response_model_exclude_none=True,
    )
    def import_input(
        command: ImportEvaluationInput,
        idempotency_key: str | None = Header(default=None, max_length=200),
    ) -> EvaluationInput:
        return lifecycle.import_input(command, idempotency_key)

    @app.get(
        "/api/v1/evaluation-inputs",
        response_model=list[EvaluationInput],
        response_model_exclude_none=True,
    )
    def list_inputs() -> list[EvaluationInput]:
        return store.list_inputs()

    @app.get(
        "/api/v1/evaluation-inputs/{input_id}",
        response_model=EvaluationInput,
        response_model_exclude_none=True,
    )
    def get_input(input_id: UUID) -> EvaluationInput:
        return lifecycle.get_input(input_id)

    @app.get("/api/v1/evaluation-inputs/{input_id}/samples")
    def preview_input(input_id: UUID) -> dict[str, Any]:
        return lifecycle.preview(input_id)

    @app.post(
        "/api/v1/evaluation-inputs/{input_id}/actions/evaluate",
        response_model=EvaluationRun,
        status_code=201,
    )
    def evaluate_input(input_id: UUID, command: EvaluateInput) -> EvaluationRun:
        return lifecycle.evaluate(input_id, command)

    @app.post(
        "/api/v1/feedback-sets/{feedback_id}/actions/send-to-catalyst",
        response_model=HandoffReceipt,
    )
    def send_feedback(feedback_id: UUID, command: SendFeedback) -> HandoffReceipt:
        return lifecycle.send_feedback(feedback_id, command)

    @app.middleware("http")
    async def propagate_trace(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        parsed_trace = parse_w3c_traceparent(request.headers.get("traceparent"))
        if parsed_trace:
            trace_id, span_id = parsed_trace
        else:
            trace_id = uuid4().hex
            span_id = "0000000000000001"

        raw_req_id = request.headers.get("x-request-id")
        request_id = sanitize_request_id(raw_req_id) or f"req-{uuid4().hex[:12]}"

        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["traceparent"] = f"00-{trace_id}-{span_id}-01"
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(EchoError)
    async def product_error(request: Request, exc: EchoError) -> JSONResponse:
        mapping = map_echo_error(exc.code)
        canonical_code = mapping["code"]
        trace_id = getattr(request.state, "trace_id", None) or uuid4().hex
        span_id = getattr(request.state, "span_id", "0000000000000001")
        request_id = getattr(request.state, "request_id", None)
        emit_diagnostic_error(
            "echo.error",
            canonical_code,
            f"{exc.title}: {exc.detail}",
            trace_id=trace_id,
            span_id=span_id,
            attributes={
                "http.target": request.url.path,
                "http.status_code": exc.status,
                "request_id": request_id,
                "cause_kind": mapping.get("cause_kind"),
                "recovery_action": mapping.get("recovery_action"),
                "legacy_code": exc.code,
            },
        )
        problem = ProblemDetails(
            type=f"https://errors.cyrene.dev/echo/{canonical_code.lower()}",
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            instance=request.url.path,
            code=exc.code,
            retryable=exc.retryable,
            trace_id=trace_id,
            resource_ref=exc.resource_ref,
            request_id=request_id,
            recovery_action=mapping.get("recovery_action"),
        )
        return JSONResponse(
            status_code=exc.status,
            content=problem.model_dump(by_alias=True, exclude_none=True, mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(EvaluationEngineFailure)
    async def engine_error(request: Request, _exc: EvaluationEngineFailure) -> JSONResponse:
        mapping = map_echo_error("ECHO_ENGINE_FAILED")
        canonical_code = mapping["code"]
        trace_id = getattr(request.state, "trace_id", None) or uuid4().hex
        span_id = getattr(request.state, "span_id", "0000000000000001")
        request_id = getattr(request.state, "request_id", None)
        emit_diagnostic_error(
            "echo.engine_failure",
            canonical_code,
            "The evaluation execution engine failed.",
            trace_id=trace_id,
            span_id=span_id,
            attributes={
                "http.target": request.url.path,
                "http.status_code": 500,
                "request_id": request_id,
                "cause_kind": mapping.get("cause_kind"),
                "recovery_action": mapping.get("recovery_action"),
            },
        )
        problem = ProblemDetails(
            type="https://errors.cyrene.dev/echo/engine-failed",
            title="Evaluation engine failed",
            status=500,
            detail="The evaluation engine failed to execute the run.",
            instance=request.url.path,
            code="ECHO_ENGINE_FAILED",
            retryable=True,
            trace_id=trace_id,
            request_id=request_id,
            recovery_action=mapping.get("recovery_action"),
        )
        return JSONResponse(
            status_code=500,
            content=problem.model_dump(by_alias=True, mode="json"),
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        mapping = map_echo_error("ECHO_REQUEST_INVALID")
        canonical_code = mapping["code"]
        trace_id = getattr(request.state, "trace_id", None) or uuid4().hex
        span_id = getattr(request.state, "span_id", "0000000000000001")
        request_id = getattr(request.state, "request_id", None)
        emit_diagnostic_error(
            "echo.validation_error",
            canonical_code,
            "The request does not conform to the Echo Product API v1 contract.",
            trace_id=trace_id,
            span_id=span_id,
            attributes={
                "http.target": request.url.path,
                "http.status_code": 422,
                "request_id": request_id,
                "cause_kind": mapping.get("cause_kind"),
                "recovery_action": mapping.get("recovery_action"),
            },
        )
        problem = ProblemDetails(
            type="https://errors.cyrene.dev/echo/request-invalid",
            title="Request validation failed",
            status=422,
            detail="The request does not conform to the Echo Product API v1 contract.",
            instance=request.url.path,
            code="ECHO_REQUEST_INVALID",
            retryable=False,
            trace_id=trace_id,
            request_id=request_id,
            recovery_action=mapping.get("recovery_action"),
        )
        return JSONResponse(
            status_code=422,
            content=problem.model_dump(by_alias=True, mode="json"),
            media_type="application/problem+json",
        )

    # ────────────────────────────────────────────────────────────────
    # SECTION: Minimal session-feedback interface (HTML)
    # ────────────────────────────────────────────────────────────────
    # 中文：最小会话反馈接口（HTML）。
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index_page() -> str:
        """Serve the minimal sample-list / score / filter / export page. | 最小界面。"""

        return INDEX_HTML

    # ────────────────────────────────────────────────────────────────
    # SECTION: EvaluationSuite + JudgeProfile
    # ────────────────────────────────────────────────────────────────
    # 中文：EvaluationSuite 与 JudgeProfile。
    @app.post(
        "/api/v1/evaluation-suites",
        response_model=EvaluationSuite,
        response_model_exclude_none=True,
        status_code=201,
    )
    def create_suite(
        command: CreateSuiteRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    ) -> EvaluationSuite:
        return service.create_suite(command, idempotency_key)

    @app.get("/api/v1/evaluation-suites/{suiteId}", response_model=EvaluationSuite)
    def get_suite(suite_id: Annotated[UUID, ApiPath(alias="suiteId")]) -> EvaluationSuite:
        return service.get_suite(suite_id)

    @app.post(
        "/api/v1/judge-profiles",
        response_model=JudgeProfile,
        response_model_exclude_none=True,
        status_code=201,
    )
    def create_judge_profile(
        command: CreateJudgeProfileRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    ) -> JudgeProfile:
        return service.create_judge_profile(command, idempotency_key)

    @app.get(
        "/api/v1/judge-profiles/{profileId}",
        response_model=JudgeProfile,
        response_model_exclude_none=True,
    )
    def get_judge_profile(
        profile_id: Annotated[UUID, ApiPath(alias="profileId")],
    ) -> JudgeProfile:
        return service.get_judge_profile(profile_id)

    # ────────────────────────────────────────────────────────────────
    # SECTION: Session import + EvaluationRun execution
    # ────────────────────────────────────────────────────────────────
    # 中文：会话导入与 EvaluationRun 执行。
    @app.post(
        "/api/v1/session-artifacts",
        response_model=ArtifactRef,
        status_code=201,
    )
    def import_sessions(
        payload: Annotated[bytes, Body(media_type="application/jsonl")],
    ) -> ArtifactRef:
        return service.import_sessions(payload)

    @app.post(
        "/api/v1/evaluation-runs",
        response_model=EvaluationRun,
        response_model_exclude_none=True,
        status_code=201,
    )
    def create_run(
        command: CreateRunRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    ) -> EvaluationRun:
        return service.create_run(command, idempotency_key)

    @app.get(
        "/api/v1/evaluation-runs/{runId}",
        response_model=EvaluationRun,
        response_model_exclude_none=True,
    )
    def get_run(run_id: Annotated[UUID, ApiPath(alias="runId")]) -> EvaluationRun:
        return service.get_run(run_id)

    @app.get("/api/v1/evaluation-results/{resultId}", response_model=EvaluationResult)
    def get_result(result_id: Annotated[UUID, ApiPath(alias="resultId")]) -> EvaluationResult:
        return service.get_result(result_id)

    @app.get("/api/v1/gate-decisions/{gateId}", response_model=GateDecision)
    def get_gate(gate_id: Annotated[UUID, ApiPath(alias="gateId")]) -> GateDecision:
        return service.get_gate(gate_id)

    # ────────────────────────────────────────────────────────────────
    # SECTION: Per-sample review, human annotation, filtering
    # ────────────────────────────────────────────────────────────────
    # 中文：逐样本审核、人工标注与筛选。
    @app.get(
        "/api/v1/evaluation-runs/{runId}/samples",
        response_model=list[SampleRecord],
    )
    def list_samples(
        run_id: Annotated[UUID, ApiPath(alias="runId")],
        only_passed: bool | None = Query(default=None),
        only_annotated: bool | None = Query(default=None),
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[SampleRecord]:
        return service.list_samples(
            run_id,
            only_passed=only_passed,
            only_annotated=only_annotated,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/api/v1/evaluation-runs/{runId}/samples/{sampleIndex}",
        response_model=SampleRecord,
    )
    def get_sample(
        run_id: Annotated[UUID, ApiPath(alias="runId")],
        sample_index: Annotated[int, ApiPath(alias="sampleIndex", ge=1)],
    ) -> SampleRecord:
        return service.get_sample(run_id, sample_index)

    @app.post(
        "/api/v1/evaluation-runs/{runId}/annotations",
        response_model=HumanAnnotation,
        status_code=201,
    )
    def annotate_sample(
        run_id: Annotated[UUID, ApiPath(alias="runId")],
        command: CreateAnnotationRequest,
    ) -> HumanAnnotation:
        return service.annotate_sample(run_id, command)

    @app.get(
        "/api/v1/evaluation-runs/{runId}/annotations",
        response_model=list[HumanAnnotation],
    )
    def list_annotations(
        run_id: Annotated[UUID, ApiPath(alias="runId")],
    ) -> list[HumanAnnotation]:
        return service.list_annotations(run_id)

    # ────────────────────────────────────────────────────────────────
    # SECTION: FeedbackSet + Catalyst-compatible export
    # ────────────────────────────────────────────────────────────────
    # 中文：FeedbackSet 与 Catalyst 兼容导出。
    @app.post(
        "/api/v1/feedback-sets",
        response_model=FeedbackSet,
        status_code=201,
    )
    def create_feedback_set(
        command: CreateFeedbackSetRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    ) -> FeedbackSet:
        return service.create_feedback_set(command, idempotency_key)

    @app.get(
        "/api/v1/feedback-sets/{feedbackSetId}",
        response_model=FeedbackSet,
    )
    def get_feedback_set(
        feedback_set_id: Annotated[UUID, ApiPath(alias="feedbackSetId")],
    ) -> FeedbackSet:
        return service.get_feedback_set(feedback_set_id)

    @app.get(
        "/api/v1/feedback-sets",
        response_model=list[FeedbackSet],
    )
    def list_feedback_sets(
        run_id: Annotated[UUID | None, Query(alias="runId")] = None,
    ) -> list[FeedbackSet]:
        return service.list_feedback_sets(run_id)

    @app.post(
        "/api/v1/feedback-sets/{feedbackSetId}/export",
        response_model=ExportFeedbackSetResponse,
        response_model_exclude_none=True,
    )
    def export_feedback_set(
        feedback_set_id: Annotated[UUID, ApiPath(alias="feedbackSetId")],
    ) -> ExportFeedbackSetResponse:
        feedback_set, _payload = service.export_feedback_set(feedback_set_id)
        return ExportFeedbackSetResponse(
            feedback_set=feedback_set,
            export_artifact=feedback_set.export_artifact,  # type: ignore[arg-type]
            candidate_count=feedback_set.candidate_count,
            handoff_status=feedback_set.handoff_status,
        )

    @app.get(
        "/api/v1/feedback-sets/{feedbackSetId}/export",
        response_class=Response,
    )
    def download_feedback_set(
        feedback_set_id: Annotated[UUID, ApiPath(alias="feedbackSetId")],
    ) -> Response:
        feedback_set, payload = service.export_feedback_set(feedback_set_id)
        return Response(
            content=payload,
            media_type="application/jsonl",
            headers={
                "Content-Disposition": (f'attachment; filename="feedback-{feedback_set.id}.jsonl"'),
            },
        )

    return app

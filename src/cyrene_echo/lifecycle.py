"""
┌─────────────────────────────────────────────────────────────────────┐
│ Module: cyrene_echo.lifecycle                                      │
│ Role: Explicit evaluation input and feedback Product handoffs.     │
│ 模块职责：引用导入评估输入，显式评估并向 Catalyst 发送选定反馈集。       │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from pydantic import Field

from cyrene_echo.domain import (
    ArtifactRef,
    ContractModel,
    CreateRunRequest,
    EvaluationInput,
    EvaluationRun,
    FeedbackHandoff,
    FeedbackHandoffStatus,
    ImportEvaluationInput,
    ProductResourceRef,
    utc_now,
)
from cyrene_echo.errors import EchoError
from cyrene_echo.service import EchoService, EvaluationReportContext, EvaluationReportSample
from cyrene_echo.workspace_auth import WorkspaceServicePrincipal


class HandoffReceipt(ContractModel):
    """Target-owned resource acknowledgement. | 目标产品资源回执。"""

    target_resource: ProductResourceRef
    status: Literal["DRAFT", "PREPARED", "STARTED"]
    open_in: str


class EvaluateInput(ContractModel):
    """Choose an existing evaluator explicitly. | 显式选择现有评估器。"""

    suite_id: UUID
    engine_binding_id: str = Field(min_length=1, max_length=200)
    reference_answers: dict[int, str] = Field(default_factory=dict, max_length=1000)


class SendFeedback(ContractModel):
    """Optionally prepare the next version of a selected Catalyst Dataset.

    中文:可选地为所选 Catalyst Dataset 准备下一版本。
    """

    # 中文:可选地为所选 Catalyst Dataset 准备下一个版本。

    dataset_id: UUID | None = None


class LifecycleActions:
    """Own evaluation preparation, while the source retains session history.

    中文:负责评估所需的数据准备,同时由 source 保留 session 历史。
    """

    # 中文:由 Echo 拥有评估准备流程,同时由来源 Product 保留会话历史。

    def __init__(
        self, service: EchoService, catalyst_url: str | None, client: httpx.Client | None = None
    ) -> None:
        self.service = service
        self.catalyst_url = catalyst_url.rstrip("/") if catalyst_url else None
        self.client = client or httpx.Client(timeout=30, trust_env=False)
        self.lock = RLock()

    def import_input(
        self,
        command: ImportEvaluationInput,
        key: str | None,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> EvaluationInput:
        path = self.service.artifacts.resolve(command.artifact)
        if not path.is_file() or path.stat().st_size > 16 * 1024**2:
            raise EchoError(
                code="ECHO_INPUT_INVALID",
                title="Invalid evaluation input",
                detail="Select a text dataset snapshot of at most 16 MiB.",
                status=422,
            )
        # Artifact kind is a producer-owned category, so the snapshot is accepted
        # on its declared format and verified content instead of a shared vocabulary.
        # 中文:Artifact kind 是由生产方拥有的类别,因此依据声明的格式和已验证内容接受快照,
        # 而不是使用共享词汇表。
        self._read_rows(command.artifact, command.format)
        if command.target_package_artifact is not None:
            self.service.artifacts.resolve(command.target_package_artifact)
        identifier = uuid4()
        digest = hashlib.sha256(command.model_dump_json().encode()).hexdigest()
        resource = EvaluationInput(
            **command.model_dump(),
            id=identifier,
            resource_ref=ProductResourceRef(
                uri=f"cyrene://echo/evaluation-inputs/{identifier}",
                id=str(identifier),
                resource_version=1,
            ),
            created_at=utc_now(),
        )
        return self.service.store.create_input(
            resource, key or "snapshot:" + digest, digest, principal
        )

    def get_input(
        self,
        identifier: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> EvaluationInput:
        resource = self.service.store.get_input(identifier, principal)
        if resource is None:
            raise EchoError(
                code="ECHO_INPUT_NOT_FOUND",
                title="Evaluation input not found",
                detail="Select an existing evaluation input.",
                status=404,
            )
        return resource

    def _read_rows(self, artifact: ArtifactRef, format_name: str) -> list[dict[str, Any]]:
        """Read and validate either a legacy Navigator snapshot or generic JSONL."""

        try:
            rows = [
                json.loads(line)
                for line in self.service.artifacts.resolve(artifact).read_text().splitlines()
                if line.strip()
            ]
            if not rows or len(rows) > 1000 or any(not isinstance(row, dict) for row in rows):
                raise ValueError("unsupported text snapshot")
            if format_name == "NAVIGATOR_TEXT_JSONL_V1":
                if any(
                    not isinstance(row.get("instruction"), str)
                    or not isinstance(row.get("output"), str)
                    for row in rows
                ):
                    raise ValueError("unsupported Navigator text snapshot")
            elif format_name == "CYRENE_REFERENCE_ACTUAL_JSONL_V1":
                sample_ids: set[str] = set()
                for row in rows:
                    sample_id = row.get("sampleId")
                    if (
                        not isinstance(sample_id, str)
                        or not sample_id.strip()
                        or len(sample_id) > 500
                        or sample_id in sample_ids
                    ):
                        raise ValueError("invalid or duplicate sampleId")
                    sample_ids.add(sample_id)
                    if any(
                        field in row and row[field] is not None and not isinstance(row[field], str)
                        for field in ("reference", "actual")
                    ):
                        raise ValueError("reference and actual must be strings when present")
            else:
                raise ValueError("unsupported evaluation input format")
            return rows
        except (ValueError, UnicodeError, OSError) as exc:
            detail = (
                "Expected one to 1000 JSONL objects with unique sampleId values and optional "
                "string reference and actual fields."
                if format_name == "CYRENE_REFERENCE_ACTUAL_JSONL_V1"
                else "Expected one to 1000 text JSONL rows with instruction and output fields."
            )
            raise EchoError(
                code="ECHO_INPUT_INVALID",
                title="Invalid evaluation input",
                detail=detail,
                status=422,
            ) from exc

    def preview(
        self,
        identifier: UUID,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> dict[str, Any]:
        resource = self.get_input(identifier, principal)
        rows = self._read_rows(resource.artifact, resource.format)
        return {
            "items": [{"sampleIndex": index + 1, "record": row} for index, row in enumerate(rows)],
            "total": len(rows),
        }

    def evaluate(
        self,
        identifier: UUID,
        command: EvaluateInput,
        principal: WorkspaceServicePrincipal | None = None,
        idempotency_key: str | None = None,
    ) -> EvaluationRun:
        with self.lock:
            resource = self.get_input(identifier, principal)
            artifact = resource.artifact
            report_context: EvaluationReportContext | None = None
            engine_source_path: Path | None = None
            rows = self._read_rows(artifact, resource.format)
            if resource.format == "CYRENE_REFERENCE_ACTUAL_JSONL_V1":
                if command.reference_answers:
                    raise EchoError(
                        code="ECHO_REFERENCE_ANSWER_INVALID",
                        title="Reference answers are immutable",
                        detail=(
                            "Provide reference values in the imported JSONL rows for the "
                            "CYRENE_REFERENCE_ACTUAL_JSONL_V1 format."
                        ),
                        status=422,
                    )
                suite = self.service.get_suite(command.suite_id, principal)
                if (
                    suite.evaluator != "exact_match.v1"
                    or command.engine_binding_id != "exact-match-plugin"
                ):
                    raise EchoError(
                        code="ECHO_REFERENCE_ACTUAL_REQUIRES_EXACT_MATCH",
                        title="Exact-match evaluator required",
                        detail=(
                            "CYRENE_REFERENCE_ACTUAL_JSONL_V1 runs through the exact-match "
                            "Plugins evaluator."
                        ),
                        status=422,
                    )
                if (suite.expected_field, suite.actual_field) != ("reference", "actual"):
                    raise EchoError(
                        code="ECHO_REFERENCE_ACTUAL_FIELDS_REQUIRED",
                        title="EvaluationSuite fields do not match the input format",
                        detail=(
                            "Use expectedField 'reference' and actualField 'actual' for "
                            "CYRENE_REFERENCE_ACTUAL_JSONL_V1."
                        ),
                        status=422,
                    )

                report_samples: list[EvaluationReportSample] = []
                evaluable_rows: list[dict[str, Any]] = []
                for sample_index, row in enumerate(rows, start=1):
                    sample_id = str(row["sampleId"])
                    if row.get("reference") is None:
                        report_samples.append(
                            EvaluationReportSample(
                                sample_id=sample_id,
                                sample_index=sample_index,
                                status="SKIPPED",
                                code="MISSING_REFERENCE",
                                message="No reference value was supplied for this sample.",
                            )
                        )
                    elif row.get("actual") is None:
                        report_samples.append(
                            EvaluationReportSample(
                                sample_id=sample_id,
                                sample_index=sample_index,
                                status="SKIPPED",
                                code="MISSING_ACTUAL",
                                message="No actual value was supplied for this sample.",
                            )
                        )
                    else:
                        report_samples.append(
                            EvaluationReportSample(
                                sample_id=sample_id,
                                sample_index=sample_index,
                                status="EVALUATED",
                            )
                        )
                        evaluable_rows.append(row)

                if not evaluable_rows:
                    raise EchoError(
                        code="NO_EVALUABLE_SAMPLES",
                        title="No evaluable samples",
                        detail=(
                            "No sample contains both a reference and an actual value. "
                            "Missing references were skipped and no score was created."
                        ),
                        status=422,
                    )
                engine_source_path = self.service.artifacts.stage_path(
                    f"{uuid4()}.evaluation-input.jsonl"
                )
                engine_source_path.write_text(
                    "\n".join(
                        json.dumps(row, ensure_ascii=False, sort_keys=True)
                        for row in evaluable_rows
                    )
                    + "\n",
                    encoding="utf-8",
                )
                assert resource.target_dataset_version is not None
                assert resource.target_package_artifact is not None
                report_context = EvaluationReportContext(
                    target_dataset_version=resource.target_dataset_version,
                    target_package_digest=resource.target_package_artifact.digest,
                    samples=tuple(report_samples),
                )
            if command.reference_answers:
                suite = self.service.get_suite(command.suite_id, principal)
                if any(
                    index < 1 or index > len(rows) or not value or len(value) > 10000
                    for index, value in command.reference_answers.items()
                ):
                    raise EchoError(
                        code="ECHO_REFERENCE_ANSWER_INVALID",
                        title="Invalid reference answer",
                        detail="Provide bounded text answers for existing sample indexes.",
                        status=422,
                    )
                if suite.expected_field == suite.actual_field:
                    raise EchoError(
                        code="ECHO_REFERENCE_ANSWER_INVALID",
                        title="Evaluation fields overlap",
                        detail="Expected and actual fields must be distinct.",
                        status=422,
                    )
                for index, answer in command.reference_answers.items():
                    rows[index - 1][suite.expected_field] = answer
                    rows[index - 1]["referenceAnswerSource"] = "echo-user-input"
                payload = (
                    "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
                ).encode()
                artifact = self.service.artifacts.publish_bytes(payload, kind="dataset")
            try:
                run = self.service.create_run(
                    CreateRunRequest(
                        suite_id=command.suite_id,
                        input_artifact=artifact,
                        engine_binding_id=command.engine_binding_id,
                    ),
                    idempotency_key or "evaluation-input:" + str(identifier),
                    engine_source_path=engine_source_path,
                    report_context=report_context,
                    principal=principal,
                )
            finally:
                if engine_source_path is not None:
                    engine_source_path.unlink(missing_ok=True)
            resource.state = "STARTED"
            resource.evaluation_run = ProductResourceRef(
                uri=f"cyrene://echo/evaluation-runs/{run.id}",
                id=str(run.id),
                resource_version=run.resource_version,
            )
            self.service.store.save("input", resource, principal)
            return run

    def send_feedback(
        self,
        identifier: UUID,
        command: SendFeedback,
        principal: WorkspaceServicePrincipal | None = None,
    ) -> HandoffReceipt:
        with self.lock:
            feedback = self.service.get_feedback_set(identifier, principal)
            persisted = self.service.store.get_feedback_handoff(identifier, principal)
            if feedback.handoff_status == FeedbackHandoffStatus.HANDLED_OFF:
                if persisted is None:
                    raise EchoError(
                        code="ECHO_CATALYST_RECEIPT_INVALID",
                        title="Catalyst receipt missing",
                        detail="The handled-off FeedbackSet has no durable target receipt.",
                        status=500,
                    )
                if persisted.dataset_id != command.dataset_id:
                    raise EchoError(
                        code="ECHO_CATALYST_HANDOFF_CONFLICT",
                        title="Catalyst handoff conflict",
                        detail="The FeedbackSet was already sent with a different dataset target.",
                        status=409,
                    )
                return HandoffReceipt(
                    target_resource=persisted.target_resource,
                    status=persisted.status,
                    open_in=persisted.open_in,
                )
            if persisted is not None:
                raise EchoError(
                    code="ECHO_CATALYST_RECEIPT_INVALID",
                    title="Catalyst receipt inconsistent",
                    detail="The durable target receipt does not match the FeedbackSet state.",
                    status=500,
                )
            if self.catalyst_url is None:
                raise EchoError(
                    code="ECHO_CATALYST_NOT_CONNECTED",
                    title="Catalyst unavailable",
                    detail="Configure the Catalyst Product URL before sending feedback.",
                    status=503,
                )
            feedback, payload = self.service.export_feedback_set(identifier, principal)
            assert feedback.export_artifact is not None
            lineage = [f"cyrene://echo/evaluation-runs/{feedback.run_id}"]
            for line in payload.decode().splitlines():
                sample = json.loads(line).get("originalSample", {})
                lineage.extend(
                    ref for ref in sample.get("provenanceRefs", []) if isinstance(ref, str)
                )
            lineage = list(dict.fromkeys(lineage))
            if len(lineage) > 100:
                raise EchoError(
                    code="ECHO_PROVENANCE_LIMIT",
                    title="Feedback selection too broad",
                    detail="Select a FeedbackSet with at most 100 distinct lineage references.",
                    status=422,
                )
            source = ProductResourceRef(
                uri=f"cyrene://echo/feedback-sets/{identifier}",
                id=str(identifier),
                resource_version=feedback.resource_version,
            )
            body: dict[str, Any] = {
                "sourceRef": source.model_dump(mode="json"),
                "artifact": feedback.export_artifact.model_dump(mode="json", exclude_none=True),
                "provenanceRefs": lineage,
            }
            if command.dataset_id is not None:
                body["datasetId"] = str(command.dataset_id)
            try:
                response = self.client.post(
                    self.catalyst_url + "/api/v1/feedback-imports",
                    json=body,
                    headers={
                        "Idempotency-Key": (
                            f"echo-feedback:{identifier}:{feedback.resource_version}"
                        )
                    },
                )
                if response.status_code != 201:
                    raise ValueError("Catalyst feedback import did not return HTTP 201")
                response.raise_for_status()
                receipt = HandoffReceipt.model_validate(response.json())
                target_id = str(UUID(receipt.target_resource.id))
                expected_uri = f"cyrene://catalyst/preparations/{target_id}"
                expected_path = f"/api/v1/preparations/{target_id}"
                if (
                    receipt.target_resource.id != target_id
                    or receipt.target_resource.uri != expected_uri
                    or receipt.open_in not in {expected_path, self.catalyst_url + expected_path}
                ):
                    raise ValueError("Catalyst returned a mismatched preparation identity")
                receipt.open_in = self.catalyst_url + expected_path
            except (httpx.HTTPError, ValueError) as exc:
                raise EchoError(
                    code="ECHO_CATALYST_HANDOFF_FAILED",
                    title="Catalyst handoff failed",
                    detail=(
                        "Catalyst did not acknowledge a dataset preparation. "
                        "Retry the same FeedbackSet."
                    ),
                    status=502,
                    retryable=True,
                ) from exc
            handled = feedback.model_copy(
                update={
                    "handoff_status": FeedbackHandoffStatus.HANDLED_OFF,
                    "updated_at": utc_now(),
                    "resource_version": feedback.resource_version + 1,
                }
            )
            handoff = FeedbackHandoff(
                id=identifier,
                source_resource_version=feedback.resource_version,
                dataset_id=command.dataset_id,
                target_resource=receipt.target_resource,
                status=receipt.status,
                open_in=receipt.open_in,
                confirmed_at=utc_now(),
            )
            self.service.store.save_feedback_handoff(handled, handoff, principal)
            return receipt

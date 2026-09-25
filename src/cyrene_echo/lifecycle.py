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
from cyrene_echo.service import EchoService


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

    def import_input(self, command: ImportEvaluationInput, key: str | None) -> EvaluationInput:
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
        # 中文:Artifact kind 是由生产方拥有的类别,因此依据声明的格式和已验证内容接受快照,而不是使用共享词汇表。
        self._rows(command.artifact)
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
        return self.service.store.create_input(resource, key or "snapshot:" + digest, digest)

    def get_input(self, identifier: UUID) -> EvaluationInput:
        resource = self.service.store.get_input(identifier)
        if resource is None:
            raise EchoError(
                code="ECHO_INPUT_NOT_FOUND",
                title="Evaluation input not found",
                detail="Select an existing evaluation input.",
                status=404,
            )
        return resource

    def _rows(self, artifact: ArtifactRef) -> list[dict[str, Any]]:
        try:
            rows = [
                json.loads(line)
                for line in self.service.artifacts.resolve(artifact).read_text().splitlines()
                if line.strip()
            ]
            if (
                not rows
                or len(rows) > 1000
                or any(
                    not isinstance(row, dict)
                    or not isinstance(row.get("instruction"), str)
                    or not isinstance(row.get("output"), str)
                    for row in rows
                )
            ):
                raise ValueError("unsupported text snapshot")
            return rows
        except (ValueError, UnicodeError, OSError) as exc:
            raise EchoError(
                code="ECHO_INPUT_INVALID",
                title="Invalid evaluation input",
                detail="Expected one to 1000 text JSONL rows with instruction and output fields.",
                status=422,
            ) from exc

    def preview(self, identifier: UUID) -> dict[str, Any]:
        rows = self._rows(self.get_input(identifier).artifact)
        return {
            "items": [{"sampleIndex": index + 1, "record": row} for index, row in enumerate(rows)],
            "total": len(rows),
        }

    def evaluate(self, identifier: UUID, command: EvaluateInput) -> EvaluationRun:
        with self.lock:
            resource = self.get_input(identifier)
            artifact = resource.artifact
            if command.reference_answers:
                suite = self.service.get_suite(command.suite_id)
                rows = self._rows(artifact)
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
            run = self.service.create_run(
                CreateRunRequest(
                    suite_id=command.suite_id,
                    input_artifact=artifact,
                    engine_binding_id=command.engine_binding_id,
                ),
                "evaluation-input:" + str(identifier),
            )
            resource.state = "STARTED"
            resource.evaluation_run = ProductResourceRef(
                uri=f"cyrene://echo/evaluation-runs/{run.id}",
                id=str(run.id),
                resource_version=run.resource_version,
            )
            self.service.store.save("input", resource)
            return run

    def send_feedback(self, identifier: UUID, command: SendFeedback) -> HandoffReceipt:
        with self.lock:
            feedback = self.service.get_feedback_set(identifier)
            persisted = self.service.store.get_feedback_handoff(identifier)
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
            feedback, payload = self.service.export_feedback_set(identifier)
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
            self.service.store.save_feedback_handoff(handled, handoff)
            return receipt

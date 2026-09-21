"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 errors.py                                                       │
│  Module: cyrene_echo.errors                                         │
│  Role: Stable Product errors and sanitized evaluator failures.      │
│                                                                     │
│  模块职责：稳定产品错误与已净化评估器失败。                              │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations


class EchoError(RuntimeError):
    """Typed error exposed through the Product API. | 产品 API 类型化错误。"""

    def __init__(
        self,
        *,
        code: str,
        title: str,
        detail: str,
        status: int,
        retryable: bool = False,
        resource_ref: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.title = title
        self.detail = detail
        self.status = status
        self.retryable = retryable
        self.resource_ref = resource_ref


class EvaluationEngineFailure(RuntimeError):
    """Sanitized replaceable-engine failure. | 可替换引擎失败。"""


# ════════════════════════════════════════════════════════════════════════
# Canonical Cyrene Echo Error Catalog & Mappings
# ════════════════════════════════════════════════════════════════════════
ECHO_ERROR_MAPPINGS: dict[str, dict[str, str]] = {
    "ECHO_REQUEST_INVALID": {
        "code": "PRODUCT.ECHO.REQUEST_INVALID",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_ARTIFACT_IDENTITY_INVALID": {
        "code": "PRODUCT.ECHO.ARTIFACT_IDENTITY_INVALID",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_ARTIFACT_UNAVAILABLE": {
        "code": "PRODUCT.ECHO.ARTIFACT_UNAVAILABLE",
        "cause_kind": "storage",
        "recovery_action": "query_state_first",
    },
    "ECHO_RUNNER_BINDING_UNKNOWN": {
        "code": "PRODUCT.ECHO.RUNNER_BINDING_UNKNOWN",
        "cause_kind": "configuration",
        "recovery_action": "fix_configuration",
    },
    "ECHO_RUNNER_BINDING_MISMATCH": {
        "code": "PRODUCT.ECHO.RUNNER_BINDING_MISMATCH",
        "cause_kind": "configuration",
        "recovery_action": "fix_configuration",
    },
    "ECHO_CATALYST_HANDOFF_FAILED": {
        "code": "PRODUCT.ECHO.CATALYST_HANDOFF_FAILED",
        "cause_kind": "network",
        "recovery_action": "safely_retry",
    },
    "ECHO_CATALYST_NOT_CONNECTED": {
        "code": "PRODUCT.ECHO.CATALYST_NOT_CONNECTED",
        "cause_kind": "configuration",
        "recovery_action": "fix_configuration",
    },
    "ECHO_INPUT_INVALID": {
        "code": "PRODUCT.ECHO.INPUT_INVALID",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_INPUT_NOT_FOUND": {
        "code": "PRODUCT.ECHO.INPUT_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_PROVENANCE_LIMIT": {
        "code": "PRODUCT.ECHO.PROVENANCE_LIMIT",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_REFERENCE_ANSWER_INVALID": {
        "code": "PRODUCT.ECHO.REFERENCE_ANSWER_INVALID",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_ANNOTATION_NOT_SELECTED": {
        "code": "PRODUCT.ECHO.ANNOTATION_NOT_SELECTED",
        "cause_kind": "validation",
        "recovery_action": "user_action_required",
    },
    "ECHO_ANNOTATION_UNKNOWN": {
        "code": "PRODUCT.ECHO.ANNOTATION_UNKNOWN",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_EVALUATION_FAILED": {
        "code": "PRODUCT.ECHO.EVALUATION_FAILED",
        "cause_kind": "execution",
        "recovery_action": "fix_configuration",
    },
    "ECHO_FEEDBACK_SAMPLE_UNKNOWN": {
        "code": "PRODUCT.ECHO.FEEDBACK_SAMPLE_UNKNOWN",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_FEEDBACK_SET_NOT_FOUND": {
        "code": "PRODUCT.ECHO.FEEDBACK_SET_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_GATE_NOT_FOUND": {
        "code": "PRODUCT.ECHO.GATE_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_JUDGE_CREDENTIAL_UNAVAILABLE": {
        "code": "PRODUCT.ECHO.JUDGE_CREDENTIAL_UNAVAILABLE",
        "cause_kind": "permission",
        "recovery_action": "fix_configuration",
    },
    "ECHO_JUDGE_PROFILE_NOT_FOUND": {
        "code": "PRODUCT.ECHO.JUDGE_PROFILE_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_RESULT_NOT_FOUND": {
        "code": "PRODUCT.ECHO.RESULT_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_RUN_NOT_FOUND": {
        "code": "PRODUCT.ECHO.RUN_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_SAMPLE_NOT_FOUND": {
        "code": "PRODUCT.ECHO.SAMPLE_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_SUITE_JUDGE_PROFILE_REQUIRED": {
        "code": "PRODUCT.ECHO.SUITE_JUDGE_PROFILE_REQUIRED",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_SUITE_NOT_FOUND": {
        "code": "PRODUCT.ECHO.SUITE_NOT_FOUND",
        "cause_kind": "not_found",
        "recovery_action": "user_action_required",
    },
    "ECHO_IDEMPOTENCY_CONFLICT": {
        "code": "PRODUCT.ECHO.IDEMPOTENCY_CONFLICT",
        "cause_kind": "conflict",
        "recovery_action": "safely_retry",
    },
    "ECHO_INPUT_RECEIPT_INVALID": {
        "code": "PRODUCT.ECHO.INPUT_RECEIPT_INVALID",
        "cause_kind": "validation",
        "recovery_action": "fix_configuration",
    },
    "ECHO_ENGINE_FAILED": {
        "code": "PRODUCT.ECHO.ENGINE_FAILED",
        "cause_kind": "execution",
        "recovery_action": "safely_retry",
    },
}


def map_echo_error(raw_code: str) -> dict[str, str]:
    """Map a raw or legacy Echo error code to canonical PRODUCT.ECHO.<REASON>."""
    if raw_code in ECHO_ERROR_MAPPINGS:
        return ECHO_ERROR_MAPPINGS[raw_code]
    normalized = raw_code.upper().replace(" ", "_")
    if not normalized.startswith("PRODUCT.ECHO."):
        clean_name = normalized.removeprefix("ECHO_")
        canonical = f"PRODUCT.ECHO.{clean_name}"
    else:
        canonical = normalized
    return {
        "code": canonical,
        "cause_kind": "unknown",
        "recovery_action": "query_state_first",
    }

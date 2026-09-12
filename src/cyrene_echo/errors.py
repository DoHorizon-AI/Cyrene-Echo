"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 errors.py                                                       │
│  Module: cyrene_echo.errors                                         │
│  Role: Stable Product errors and sanitized evaluator failures.      │
│                                                                     │
│  模块职责：稳定产品错误与已净化评估器失败。                              │
└─────────────────────────────────────────────────────────────────────┘
"""


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

"""
Tests for Echo W3C trace correlation, secret redaction, structured logging,
and canonical error code mappings.

中文：测试 Echo 的 W3C trace 关联、敏感信息脱敏、结构化日志和规范错误码映射。
"""
# 中文：测试 Echo 的 W3C trace 关联、密钥脱敏、结构化日志和规范错误代码映射。

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from cyrene_echo.api import create_app
from cyrene_echo.errors import (
    ECHO_ERROR_MAPPINGS,
    map_echo_error,
)
from cyrene_echo.logging import (
    MAX_RECORD_BYTES,
    emit_diagnostic_error,
    format_cyrene_log,
    is_sensitive_key,
    parse_w3c_traceparent,
    redact_attributes,
    sanitize_correlation_id,
    sanitize_request_id,
)


def test_parse_w3c_traceparent_valid() -> None:
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id = "00f067aa0ba902b7"
    raw = f"00-{trace_id}-{span_id}-01"
    parsed = parse_w3c_traceparent(raw)
    assert parsed == (trace_id, span_id)


def test_parse_w3c_traceparent_invalid() -> None:
    assert parse_w3c_traceparent(None) is None
    assert parse_w3c_traceparent("") is None
    assert parse_w3c_traceparent("invalid-header") is None
    assert parse_w3c_traceparent(f"00-{'0' * 32}-{'1' * 16}-01") is None
    assert parse_w3c_traceparent(f"00-{'1' * 32}-{'0' * 16}-01") is None


def test_sanitize_correlation_id() -> None:
    assert sanitize_correlation_id(None) is None
    assert sanitize_correlation_id("") is None
    assert sanitize_correlation_id("   ") is None
    assert sanitize_correlation_id("req-123_abc.XYZ") == "req-123_abc.XYZ"
    assert sanitize_correlation_id("req<bad>!*&^123") == "reqbad123"

    long_id = "a" * 200
    sanitized = sanitize_request_id(long_id)
    assert sanitized is not None
    assert len(sanitized) == 128


def test_secret_redaction_and_token_preservation() -> None:
    assert is_sensitive_key("authorization")
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("client-secret")
    assert is_sensitive_key("password")

    assert not is_sensitive_key("tokens")
    assert not is_sensitive_key("prompt_tokens")
    assert not is_sensitive_key("completion_tokens")
    assert not is_sensitive_key("token_count")

    data = {
        "auth_token": "secret123",
        "api_key": "key456",
        "tokens": 42,
        "prompt_tokens": 10,
        "nested": {
            "password": "pass",
            "token_count": 100,
        },
    }
    redacted = redact_attributes(data)
    assert redacted["auth_token"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["tokens"] == 42
    assert redacted["prompt_tokens"] == 10
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["token_count"] == 100


def test_structured_ndjson_log_formatting() -> None:
    line = format_cyrene_log(
        "INFO",
        "evaluation.started",
        "Evaluation run initiated",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
        attributes={"run_id": "run-123", "secret": "hide-me"},
    )
    assert "\n" not in line
    record = json.loads(line)
    assert record["schema_version"] == 1
    assert record["level"] == "INFO"
    assert record["event.name"] == "evaluation.started"
    assert record["service.name"] == "cyrene-echo"
    assert "timestamp" in record
    assert record["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert record["span_id"] == "00f067aa0ba902b7"
    assert record["attributes"]["run_id"] == "run-123"
    assert record["attributes"]["secret"] == "[REDACTED]"


def test_oversized_log_record_truncation() -> None:
    huge_attrs = {f"k_{i}": "v" * 1000 for i in range(50)}
    line = format_cyrene_log(
        "WARN",
        "echo.warning",
        "Large payload",
        attributes=huge_attrs,
    )
    assert len(line.encode("utf-8")) <= MAX_RECORD_BYTES
    record = json.loads(line)
    assert record["attributes"] == {"truncated": True}


def test_emit_diagnostic_error_writes_to_stderr() -> None:
    old_stderr = sys.stderr
    sys.stderr = buffer = io.StringIO()
    try:
        emit_diagnostic_error(
            "echo.error",
            "PRODUCT.ECHO.SUITE_NOT_FOUND",
            "Evaluation suite not found",
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            attributes={"suite_id": "suite-abc"},
        )
    finally:
        sys.stderr = old_stderr

    output = buffer.getvalue()
    assert output.endswith("\n")
    record = json.loads(output.strip())
    assert record["level"] == "ERROR"
    assert record["event.name"] == "echo.error"
    assert record["attributes"]["error.code"] == "PRODUCT.ECHO.SUITE_NOT_FOUND"
    assert record["attributes"]["suite_id"] == "suite-abc"


def test_echo_error_mappings() -> None:
    for raw_code, expected in ECHO_ERROR_MAPPINGS.items():
        mapped = map_echo_error(raw_code)
        assert mapped["code"] == expected["code"]
        assert mapped["cause_kind"] == expected["cause_kind"]
        assert mapped["recovery_action"] == expected["recovery_action"]

    # Unknown code fallback
    # 中文：未知代码的回退处理。
    fallback = map_echo_error("ECHO_CUSTOM_REASON")
    assert fallback["code"] == "PRODUCT.ECHO.CUSTOM_REASON"
    assert fallback["cause_kind"] == "unknown"
    assert fallback["recovery_action"] == "query_state_first"


def test_api_traceparent_propagation_and_problem_details(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "echo.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )
    client = TestClient(app)

    # 1. Custom incoming traceparent and request_id
    # 中文：1. 自定义传入的 traceparent 和 request_id。
    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    incoming_span_id = "00f067aa0ba902b7"
    incoming_traceparent = f"00-{incoming_trace_id}-{incoming_span_id}-01"
    incoming_req_id = "custom-req-789"

    old_stderr = sys.stderr
    sys.stderr = buffer = io.StringIO()
    try:
        response = client.get(
            f"/api/v1/evaluation-suites/{uuid4()}",
            headers={
                "traceparent": incoming_traceparent,
                "x-request-id": incoming_req_id,
            },
        )
    finally:
        sys.stderr = old_stderr

    assert response.status_code == 404
    assert response.headers["x-request-id"] == incoming_req_id
    assert response.headers["traceparent"] == f"00-{incoming_trace_id}-{incoming_span_id}-01"

    body = response.json()
    assert body["traceId"] == incoming_trace_id
    assert body["requestId"] == incoming_req_id
    assert body["code"] == "ECHO_SUITE_NOT_FOUND"
    assert body["recoveryAction"] == "user_action_required"
    assert "type" in body
    assert "https://errors.cyrene.dev/echo/product.echo.suite_not_found" in body["type"]

    # Verify diagnostic error on stderr
    # 中文：验证诊断错误是否已输出到 stderr。
    log_output = buffer.getvalue()
    assert "PRODUCT.ECHO.SUITE_NOT_FOUND" in log_output

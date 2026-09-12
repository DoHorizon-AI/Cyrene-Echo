"""Bind Echo tests to the exact Plugins-owned evaluation implementation."""

from __future__ import annotations

import os
from typing import Any

_SERVERS: list[Any] = []
_CONNECTION_ENV = "CYRENE_EVALUATION_RUNNER_CONNECTION_REF"


def pytest_configure() -> None:
    """Start the canonical evaluation.runner.v1 package through its direct endpoint."""

    try:
        from cyrene_plugin_runtime import serve
        from exact_match_evaluator import ExactMatchEvaluationRunner
    except ImportError as exc:  # pragma: no cover - dependency failure is explicit
        raise RuntimeError(
            "Echo tests require the exact pinned Plugins runtime and exact-match owner package"
        ) from exc

    server, connection_ref = serve(
        ExactMatchEvaluationRunner(),
        "evaluation.runner.v1",
        "1",
        "127.0.0.1:0",
    )
    _SERVERS.append(server)
    os.environ[_CONNECTION_ENV] = connection_ref


def pytest_unconfigure() -> None:
    """Stop the canonical Plugin endpoint after the test session."""

    os.environ.pop(_CONNECTION_ENV, None)
    for server in _SERVERS:
        server.stop(grace=None).wait()
    _SERVERS.clear()

"""
┌─────────────────────────────────────────────────────────────────────┐
│ Module: cyrene_echo.server                                         │
│ Role: Operator bootstrap for the independent Echo Product API.      │
│ 模块职责：独立启动 Echo，并显式配置本地 Artifact 适配与接收产品。     │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

import uvicorn

from cyrene_echo.api import create_app
from cyrene_echo.store import EchoStore

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _validated_serve_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject a listener or database the operator cannot actually serve.

    中文：拒绝 operator 实际无法运行的 listener 或数据库。
    """
# 中文：拒绝操作员无法实际提供服务的监听器或数据库。

    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.host not in LOOPBACK_HOSTS and not args.allow_remote:
        parser.error("non-loopback listeners require --allow-remote and an external TLS terminator")
    parent = args.database.expanduser().resolve().parent
    if not parent.is_dir():
        parser.error(f"--database parent directory does not exist: {parent}")


def _run_show(args: argparse.Namespace) -> int:
    """Print one persisted EvaluationRun and its gate decision.

    中文：输出已持久化的 EvaluationRun 及其 gate 判定。
    """
# 中文：打印一条已持久化的 EvaluationRun 及其 gate 决策。

    store = EchoStore(args.database.expanduser().resolve())
    try:
        run = store.get_run(UUID(args.run_id))
        if run is None:
            print(f"evaluation run not found: {args.run_id}", file=sys.stderr)
            return 1
        payload: dict[str, object] = {"run": run.model_dump(by_alias=True, mode="json")}
        gate = store.get_gate(run.gate_id) if run.gate_id else None
        if gate is not None:
            payload["gate"] = gate.model_dump(by_alias=True, mode="json")
    finally:
        store.close()
    print(json.dumps(payload, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Cyrene Echo Product API")
    commands = value.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Run the Echo Product API")
    serve.add_argument("--database", type=Path, required=True)
    serve.add_argument("--artifact-root", type=Path, required=True)
    serve.add_argument("--catalyst-url")
    serve.add_argument("--judge-token-env", help="Name of the configured judge credential variable")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8094, type=int)
    serve.add_argument("--allow-remote", action="store_true")

    run = commands.add_parser("run", help="Query persisted evaluation runs")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    show = run_commands.add_parser("show")
    show.add_argument("--database", type=Path, required=True)
    show.add_argument("--run-id", required=True)
    return value


def main() -> None:
    """Keep local operator paths out of Product handoff payloads. | 配置仅留在运维入口。"""
    parser_instance = parser()
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["serve", *argv]
    args = parser_instance.parse_args(argv)
    if args.command == "run":
        raise SystemExit(_run_show(args))
    _validated_serve_arguments(parser_instance, args)
    token = os.environ.get(args.judge_token_env) if args.judge_token_env else None
    if args.judge_token_env and not token:
        parser_instance.error("The configured judge credential variable is empty")
    app = create_app(
        database_path=args.database,
        artifact_root=args.artifact_root,
        catalyst_url=args.catalyst_url,
        judge_bearer_token=token,
    )
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()

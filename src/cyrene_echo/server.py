"""
┌─────────────────────────────────────────────────────────────────────┐
│ Module: cyrene_echo.server                                         │
│ Role: Operator bootstrap for the independent Echo Product API.      │
│ 模块职责：独立启动 Echo，并显式配置本地 Artifact 适配与接收产品。     │
└─────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from cyrene_echo.api import create_app


def main() -> None:
    """Keep local operator paths out of Product handoff payloads. | 配置仅留在运维入口。"""
    parser = argparse.ArgumentParser(description="Cyrene Echo Product API")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--catalyst-url")
    parser.add_argument(
        "--judge-token-env", help="Name of the configured judge credential variable"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8094, type=int)
    args = parser.parse_args()
    token = os.environ.get(args.judge_token_env) if args.judge_token_env else None
    if args.judge_token_env and not token:
        parser.error("The configured judge credential variable is empty")
    app = create_app(
        database_path=args.database,
        artifact_root=args.artifact_root,
        catalyst_url=args.catalyst_url,
        judge_bearer_token=token,
    )
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)

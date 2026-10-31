# Contributing to Cyrene-Echo

Echo is a Product repository. Keep evaluation state, evidence, gate decisions,
annotations, and explicit feedback selection here. Dataset state, training,
serving, generic lifecycle, and reusable evaluation implementations belong to
their canonical owners. Read the [Cyrene Contribution
Workflow](https://github.com/DoHorizon-AI/Cyrene-Platform/blob/main/docs/governance/contribution-workflow.md)
before opening a pull request.

## Local verification

From the repository root, run:

```bash
uv sync --frozen --group dev
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests
uv run --no-sync mypy
uv run --no-sync pytest -q tests
uv run --no-sync openapi-spec-validator contracts/product/v1/openapi.yaml
uv build
```

GitHub Actions in `.github/workflows/` owns automatic source and contract
checks. The Azure pipeline is a manual supplemental lane for deployment,
protected resources, or private integration; it does not replace the
public-source checks.

## Documentation, dependencies, and security

- Add or substantially change `docs/` pages in English and Chinese, and update
  [`docs/README.md`](docs/README.md).
- Keep `uv.lock` consistent with `pyproject.toml`. Review
  [`docs/DEPENDENCY-LICENSES.md`](docs/DEPENDENCY-LICENSES.md) before adding a
  dependency or changing a pinned upstream revision.
- Never commit credentials, private endpoints, tenant data, model outputs, or
  developer-specific absolute paths. See [`SECURITY.md`](SECURITY.md).
- Preserve the Apache-2.0 notice in [`LICENSE`](LICENSE) and retain upstream
  notices when distributing built artifacts.

## Task lifecycle / 任务生命周期

All contributors and coding agents must follow [AGENTS.md](AGENTS.md) and the shared
[Cyrene task lifecycle requirements](https://github.com/DoHorizon-AI/Cyrene-Workspace/blob/develop/docs/TASK_LIFECYCLE.md).

所有贡献者和 AI 编码代理均须遵循 [AGENTS.md](AGENTS.md) 与共享的
[Cyrene 任务生命周期要求](https://github.com/DoHorizon-AI/Cyrene-Workspace/blob/develop/docs/TASK_LIFECYCLE.md)。

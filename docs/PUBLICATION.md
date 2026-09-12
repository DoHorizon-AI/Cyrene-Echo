# Public-source publication note / 公开源码发布说明

## Current position / 当前状态

Echo is prepared as a `PUBLIC_PRODUCT` clean-root source snapshot. The
machine-readable policy and service manifest describe the intended target
visibility as `public`; the canonical replacement is created and verified
privately before the repository owner performs an explicit visibility switch
and read-back. The former development history, branches, pull-request refs,
tags, and local reflogs remain only in a private history archive.

Echo 已按 `PUBLIC_PRODUCT` clean-root 源码快照准备。机器可读策略与服务清单将目标可见性
描述为 `public`；canonical replacement 会先以私有状态创建并验证，再由仓库所有者明确切换
可见性并回读。此前的开发历史、分支、pull request 引用、tag 与本地 reflog 仅保存在私有历史
归档中。

The integration model is `develop` for daily work and `main` for releases. The
automatic source and Product contract checks are the GitHub Actions workflows
under `.github/workflows/`. The Azure pipeline is a manual supplemental lane
for deployment, protected resources, or private integration; it is not the
automatic CI authority.

日常集成分支为 `develop`，发布分支为 `main`。自动源码与产品契约检查由
`.github/workflows/` 下的 GitHub Actions workflow 负责。Azure pipeline 仅作为部署、受保护
资源或私有集成的手动补充通道，不是自动 CI 权威。

## Evidence boundary / 证据边界

| Surface | Current honest status | What it does not prove |
| --- | --- | --- |
| Product API, SQLite state, ArtifactRef, annotations, and exports | Local implementation and tests | Hosted exact-SHA execution or production deployment |
| `evaluation.runner.v1` exact-match path | Direct Plugins seam with local endpoint coverage | A live external evaluator or production tenant boundary |
| Exchange judge | Explicit adapter, `WIRED_NOT_RUN` without endpoint and bearer credential | Live judge correctness or availability |
| Catalyst handoff | Explicit direct handoff, `WIRED_NOT_RUN` without reachable target | Catalyst ingestion or DatasetVersion publication |
| Release automation | No repository release workflow is present | A published package or immutable release tag |

| 表面 | 当前真实状态 | 不能证明什么 |
| --- | --- | --- |
| Product API、SQLite 状态、ArtifactRef、标注与导出 | 本地实现与测试 | hosted exact-SHA 执行或生产部署 |
| `evaluation.runner.v1` exact-match 路径 | Plugins 直连接缝，有本地端点覆盖 | 真实外部评估器或生产租户边界 |
| Exchange 判官 | 显式适配器；无端点与 bearer credential 时为 `WIRED_NOT_RUN` | 判官真实正确性或可用性 |
| Catalyst 交接 | 显式直连交接；目标不可达时为 `WIRED_NOT_RUN` | Catalyst 已摄取或 DatasetVersion 已发布 |
| 发布自动化 | 当前没有仓库级发布 workflow | 已发布包或不可变 release tag |

The status names in [`API.md`](API.md), contracts, and examples describe
local implementation or wiring evidence. They must not be read as live judge,
Catalyst, hosted CI, security, or release acceptance. Test doubles remain test
fixtures and fail-closed bindings remain explicit.

[`API.md`](API.md)、契约与示例中的状态名称只描述本地实现或接线证据，不代表真实判官、
Catalyst、hosted CI、安全或发布验收。测试替身仍仅是测试夹具，fail-closed 绑定仍必须显式
配置。

## Publication blockers / 公开发布阻塞项

1. The Plugins runtime and exact-match evaluator are locked git dependencies;
   their upstream manifests currently do not declare licenses. They must receive
   explicit license metadata and be publicly cloneable.
2. The locked Plugins revision must be reachable from an anonymous clean clone;
   otherwise `uv sync --locked` cannot be reproduced after a visibility switch.
3. A fresh exact-SHA GitHub Actions run must execute real jobs and pass. A
   zero-step, quota, credential, or skipped result is `NOT_RUN`/`BLOCKED`, not
   `PASS`.
4. A package release still needs a maintainer-owned version/tag and release
   workflow; `automated_release` remains false until that exists.

1. Plugins runtime 与 exact-match evaluator 是锁定的 git 依赖，但其上游 manifest 当前都
   没有声明许可证。必须补齐明确许可证元数据，并确保依赖可公开克隆。
2. 锁定的 Plugins revision 必须能从匿名 clean clone 获取，否则切换可见性后无法复现
   `uv sync --locked`。
3. 必须有一次针对精确 SHA、实际执行 job 并通过的 GitHub Actions 运行。零步骤、配额、
   凭据或 skipped 结果均属于 `NOT_RUN`/`BLOCKED`，不能写成 `PASS`。
4. 包发布仍需要维护者指定版本/tag 并提供 release workflow；在 workflow 存在前，
   `automated_release` 保持 false。

See [`DEPENDENCY-LICENSES.md`](DEPENDENCY-LICENSES.md) for the license and
SBOM entrypoint, and [`SECURITY.md`](../SECURITY.md) for the security boundary.

许可证与 SBOM 入口见 [`DEPENDENCY-LICENSES.md`](DEPENDENCY-LICENSES.md)，安全边界见
[`SECURITY.md`](../SECURITY.md)。

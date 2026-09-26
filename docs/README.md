# Echo Documentation

Echo 文档索引 / Documentation index for Echo.

## Repository scope / 仓库范围

Echo is the Cyrene Product for model and session evaluation, quality gates,
human review, and explicit feedback handoff. The runtime under
`src/cyrene_echo/` is implemented and tested; the live Exchange judge and live
Catalyst handoff remain `WIRED_NOT_RUN` without a reachable endpoint and
credential. There is no `legacy/navigator-feedback` tree in this checkout.

Echo 是 Cyrene 的模型与会话评估、质量门禁、人工评审与显式反馈交接产品。
`src/cyrene_echo/` 运行时已实现并有测试覆盖；没有可达端点与凭证时，真实 Exchange
判官与真实 Catalyst 交接保持 `WIRED_NOT_RUN`。当前检出中不存在
`legacy/navigator-feedback` 目录。

The canonical public-source snapshot is a clean-root replacement: one
parentless `main` commit with no former branches, pull-request refs, tags, or
reflogs. Complete development history is retained only in a private recovery
archive. The hosting visibility setting and later package or binary release
remain explicit owner-controlled gates.

canonical 公开源码快照采用 clean-root 替换：只有一个无父的 `main` 提交，不带此前的分支、
pull request 引用、tag 或 reflog。完整开发历史仅保留在私有恢复归档中。托管可见性以及之后的
包或二进制发布仍是由所有者明确控制的独立门禁。

## Reading map / 阅读地图

| Path | Responsibility / 职责 |
|---|---|
| [`architecture/overview.md`](architecture/overview.md) | Evaluation boundary, runner profiles, and result lifecycle / 评估边界、运行器配置档与结果生命周期 |
| [`architecture/tool-system.md`](architecture/tool-system.md) | Runner seams, dispatch sequence, and non-ownership rules / 运行器接缝、分发时序与非归属规则 |
| [`architecture/mcp-integration.md`](architecture/mcp-integration.md) | MCP-facing evaluation adapter boundary / 面向 MCP 的评估适配边界 |
| [`modules/echo/README.md`](modules/echo/README.md) | Repository module map and recommended reading order / 仓库模块地图与推荐阅读顺序 |
| [`glossary.md`](glossary.md) | Bilingual evaluation vocabulary / 双语评估术语 |
| [`faq.md`](faq.md) | Common questions and troubleshooting / 常见问题与排障指南 |
| [`API.md`](API.md) | Product API, runner profiles, and contract status / 产品 API、运行器配置档与契约状态 |
| [`REPOSITORY-LIFECYCLE.md`](REPOSITORY-LIFECYCLE.md) | Lifecycle, governance, clean-root, and release boundaries / 生命周期、治理、clean-root 与发布边界 |
| [`PUBLICATION.md`](PUBLICATION.md) | Public-source target, evidence boundary, and blockers / 公开源码目标、证据边界与阻塞项 |
| [`DEPENDENCY-LICENSES.md`](DEPENDENCY-LICENSES.md) | Direct dependency licenses and SBOM entrypoint / 直接依赖许可证与 SBOM 入口 |
| [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) | First-party and upstream notice boundary / 一方与上游声明边界 |
| [`logging-and-errors.md`](logging-and-errors.md) | Cross-repository logging, error codes, and diagnostics specification / 跨仓日志、错误码与诊断规范 (草案 v0.1) |

## Suggested order / 推荐顺序

1. Read [`architecture/overview.md`](architecture/overview.md) for the evaluation domain and target boundaries.
2. Read [`architecture/tool-system.md`](architecture/tool-system.md) for runner seams and dispatch rules.
3. Read [`modules/echo/README.md`](modules/echo/README.md) to locate the runtime, tests, and contracts.
4. Use [`API.md`](API.md), [`REPOSITORY-LIFECYCLE.md`](REPOSITORY-LIFECYCLE.md), [`glossary.md`](glossary.md), and [`faq.md`](faq.md) as references.

1. 先阅读 [`architecture/overview.md`](architecture/overview.md)，了解评估领域与目标边界。
2. 再阅读 [`architecture/tool-system.md`](architecture/tool-system.md)，了解运行器接缝与分发规则。
3. 阅读 [`modules/echo/README.md`](modules/echo/README.md)，定位运行时、测试与契约。
4. 按需查阅 [`API.md`](API.md)、[`REPOSITORY-LIFECYCLE.md`](REPOSITORY-LIFECYCLE.md)、[`glossary.md`](glossary.md) 与 [`faq.md`](faq.md)。

## Change boundary / 变更边界

This publication pass changes only licenses, documentation, and governance
metadata. It does not change runtime behavior, API contracts, dependency
versions, lockfiles, or CI execution steps.

本次公开发布准备只修改许可证、Markdown 文档与治理元数据，不改变运行时行为、API 契约、
依赖版本、lockfile 或 CI 执行步骤。

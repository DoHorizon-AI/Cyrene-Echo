# Echo

Echo is the Cyrene Product for model and session evaluation, quality gates,
human review, and explicit feedback handoff.

## Documentation and contracts

- [Product API and evaluation contract](docs/API.md)
- [Repository lifecycle and ownership](docs/REPOSITORY-LIFECYCLE.md)
- [Session feedback example](docs/session-feedback-example.md)
- [Service manifest](service.json)
- [Public-source publication note](docs/PUBLICATION.md)
- [Dependency licenses and SBOM](docs/DEPENDENCY-LICENSES.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)
- [License](LICENSE)

## Current boundary

Echo owns evaluation lifecycle state, result evidence, gate decisions,
annotations, and selected feedback exports. It can evaluate immutable artifacts
produced by other Products and can call a live serving or judge endpoint through
an explicitly configured Product adapter.

`EvaluationExecutionPort` keeps execution replaceable. Exact-match records are
sent to the Plugins-owned `evaluation.runner.v1` endpoint identified by
`CYRENE_EVALUATION_RUNNER_CONNECTION_REF`; missing or invalid bindings fail
closed. Catalyst and Exchange are contacted through direct Product handoffs,
and evaluation business payloads never traverse a Platform service.

The exact-match Plugin and Echo adapter have real local DirectPluginRuntime
endpoint coverage. This is not production deployment evidence. The live
Exchange judge path remains `WIRED_NOT_RUN` without a reachable endpoint and
credential; test doubles are never reported as live judge acceptance. A
confirmed Catalyst handoff is persisted as `HANDLED_OFF`, and identical
replays return the durable target receipt without a second downstream call.

This repository is prepared for public-source publication, but the hosting
visibility switch is an explicit owner operation. Check
[`docs/PUBLICATION.md`](docs/PUBLICATION.md) for the remaining dependency,
license, and evidence gates.

## Clean-root history boundary

The public-source snapshot is intended to be published from one parentless
`main` root. The former development history, branches, pull-request refs, and
local reflogs belong only in a private history archive; they are not part of
the canonical public repository. Source visibility, package/binary release,
live evaluator evidence, and hosted CI are separate gates.

## Clean-root 历史边界

公开源码快照应从一个无父的 `main` 根提交发布。此前的开发历史、分支、pull request
引用与本地 reflog 只保存在私有历史归档中，不属于 canonical 公开仓库。源码可见性、包/二进制
发布、真实评估器证据与 hosted CI 是彼此独立的门禁。
---
<!-- Chinese Translation / 中文翻译 -->

# Echo

Echo 是 Cyrene 中负责模型与会话评估、质量门禁、人工审核和显式反馈交接的 Product。

## 文档与契约

- [Product API 与评估契约](docs/API.md)
- [仓库生命周期与所有权](docs/REPOSITORY-LIFECYCLE.md)
- [会话反馈示例](docs/session-feedback-example.md)
- [服务清单](service.json)
- [公开源码发布说明](docs/PUBLICATION.md)
- [依赖许可证与 SBOM](docs/DEPENDENCY-LICENSES.md)
- [第三方声明](THIRD_PARTY_NOTICES.md)
- [安全策略](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)
- [许可证](LICENSE)

## 当前边界

Echo 拥有评估生命周期状态、结果证据、门禁决策、标注和选定的反馈导出。它可以评估其他 Product 生成的不可变制品，也可以通过显式配置的 Product 适配器调用在线服务或 judge 端点。

`EvaluationExecutionPort` 让执行实现可替换。精确匹配记录会发送到由 `CYRENE_EVALUATION_RUNNER_CONNECTION_REF` 标识的 Plugins 所有 `evaluation.runner.v1` 端点。binding 缺失或无效时按 fail-closed 处理。Catalyst 与 Exchange 通过 Product 直连交接；评估业务负载不会经过 Platform 服务。

精确匹配 Plugin 与 Echo 适配器已通过真实本地 DirectPluginRuntime 端点覆盖，但这不构成生产部署证据。没有可访问端点和凭据时，在线 Exchange judge 路径仍为 `WIRED_NOT_RUN`；测试替身不会被报告为在线 judge 验收。Catalyst 交接确认后会持久化为 `HANDLED_OFF`；相同请求重放时返回持久化的目标回执，不会再次调用下游。

本仓库已准备公开源码发布，但是否切换托管可见性由 owner 显式操作。剩余依赖、许可证和证据门禁见 [`docs/PUBLICATION.md`](docs/PUBLICATION.md)。

## clean-root 历史边界

公开源码快照应从一个无父的 `main` 根提交发布。此前开发历史、分支、Pull Request 引用和本地 reflog 仅归私有历史归档所有，不属于公开规范仓库。源码可见性、包/二进制发布、在线评估器证据与 Hosted CI 是彼此独立的门禁。

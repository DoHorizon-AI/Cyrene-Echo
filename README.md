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

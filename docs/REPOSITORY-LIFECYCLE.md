# Repository Lifecycle: cyrene-echo / 仓库生命周期：cyrene-echo

This document records the current lifecycle, ownership, and publication
boundary for the Echo Product. The machine-readable authority is
[`repository-policy.yaml`](../repository-policy.yaml).

本文记录 Echo 产品当前的生命周期、职责与公开发布边界。机器可读权威文件是
[`repository-policy.yaml`](../repository-policy.yaml)。

The canonical publication form is a clean-root replacement with one
parentless `main` commit and no former branches, pull-request refs, tags, or
reflogs. The complete pre-publication history is retained in a private archive
for recovery and audit; it is not part of the public-source tree.

canonical 发布形式是 clean-root replacement：只有一个无父的 `main` 提交，不带此前的分支、
pull request 引用、tag 或 reflog。公开前的完整历史保存在私有归档中用于恢复与审计，不属于公开
源码树。

## 1. Purpose and ownership / 目的与职责

Echo is a `PUBLIC_PRODUCT` source component and Python package for evaluation
suites, runs, results, gates, human annotations, and explicitly selected
feedback-set exports. It uses provider-neutral `ArtifactRef` values and direct
Product handoffs.

Echo 是用于评估套件、运行、结果、门禁、人工标注与显式选择反馈集导出的
`PUBLIC_PRODUCT` 源码组件与 Python 包。它使用与提供方无关的 `ArtifactRef` 和产品直连
交接。

It does not own Catalyst dataset state, Yield training, Reactor serving,
Platform generic lifecycle or Artifact Plane mechanisms, or the reusable
`evaluation.runner.v1` implementation.

它不负责 Catalyst 数据集状态、Yield 训练、Reactor 服务、Platform 通用生命周期或制品
平面机制，也不负责可复用的 `evaluation.runner.v1` 实现。

## 2. Classification and release units / 分类与发布单元

| Field | Value |
| --- | --- |
| Lifecycle class | `PUBLIC_PRODUCT` |
| Publication target visibility | `public` |
| Live hosting status | May remain `private` until an explicit owner switch and read-back |
| Source owner | Cyrene Evaluation Product Team |
| Independent build | Yes: Python 3.12 and `uv` |
| Package unit | `cyrene-echo` |
| Release role | `COMPONENT_RELEASE` |
| Standalone user product | No; consumed as a Cyrene distribution component |
| Remote default branch | `main` |
| Integration branch | `develop` |
| Release branch | `main` |

| 字段 | 值 |
| --- | --- |
| 生命周期分类 | `PUBLIC_PRODUCT` |
| 公开发布目标可见性 | `public` |
| 当前托管状态 | 在所有者明确切换并回读前可能仍为 `private` |
| 源码所有者 | Cyrene Evaluation Product Team |
| 独立构建 | 是：Python 3.12 与 `uv` |
| 包单元 | `cyrene-echo` |
| 发布角色 | `COMPONENT_RELEASE` |
| 独立用户产品 | 否；作为 Cyrene 分发组件被消费 |
| 远程默认分支 | `main` |
| 集成分支 | `develop` |
| 发布分支 | `main` |

## 3. CI and release authorities / CI 与发布权威

GitHub Actions is the `github` authority for automatic source and Product
contract checks. The workflows are [`ci.yml`](../.github/workflows/ci.yml) and
[`product-contract.yml`](../.github/workflows/product-contract.yml).

GitHub Actions 是自动源码与产品契约检查的 `github` 权威，workflow 为
[`ci.yml`](../.github/workflows/ci.yml) 与
[`product-contract.yml`](../.github/workflows/product-contract.yml)。

The Azure definition is a manual supplemental lane for deployment, protected
resources, or private integration. It is not the automatic CI authority. No
repository release workflow is present on the current branch; `github_releases`
remains the planned release authority and `automated_release` is false until a
maintainer-owned release workflow and read-back evidence exist.

Azure 定义是部署、受保护资源或私有集成的手动补充通道，不是自动 CI 权威。当前分支没有
仓库级 release workflow；`github_releases` 仍是计划中的发布权威，在维护者提供 release
workflow 与回读证据前，`automated_release` 保持 false。

## 4. Public-source boundary / 公开源码边界

The target is a public clean-root source clone with no private checkout, credential,
tenant data, model output, or deployment secret required for the local
CPU-oriented checks. The locked Plugins runtime and exact-match evaluator are
git dependencies; their anonymous cloneability and license metadata must be
confirmed before the hosting setting is switched.

目标是公开 clean-root 源码克隆后无需私有 checkout、凭据、租户数据、模型输出或部署密钥即可
运行以 CPU 为主的本地检查。锁定的 Plugins runtime 与 exact-match evaluator 是 git 依赖；在
切换托管可见性前，必须确认它们可匿名克隆并有明确许可证元数据。

The detailed dependency and SBOM record is
[`DEPENDENCY-LICENSES.md`](DEPENDENCY-LICENSES.md). Echo's Apache-2.0 license
applies to Echo-owned files only; it does not relicense the Plugins packages.

详细依赖与 SBOM 记录见 [`DEPENDENCY-LICENSES.md`](DEPENDENCY-LICENSES.md)。Echo 的
Apache-2.0 仅适用于 Echo 自有文件，不会重新授权 Plugins 包。

## 5. Evidence and maturity / 证据与成熟度

Local tests establish the Product API, SQLite state, ArtifactRef handling,
deterministic evaluation, annotations, and export behavior. They do not by
themselves establish hosted exact-SHA CI, a live Exchange judge, Catalyst
ingestion, production security, or a published package.

本地测试建立产品 API、SQLite 状态、ArtifactRef 处理、确定性评估、标注与导出行为证据，
但不能单独证明 hosted exact-SHA CI、Exchange 真实判官、Catalyst 摄取、生产安全或已发布包。

`WIRED_NOT_RUN`, skipped, zero-step, quota-blocked, and credential-blocked
results retain those meanings and must not be reported as `PASS`. Test doubles
are fixtures only. See [`PUBLICATION.md`](PUBLICATION.md) for the status matrix.

`WIRED_NOT_RUN`、skipped、zero-step、配额阻塞与凭据阻塞必须保留原有含义，不能报告为
`PASS`。测试替身仅是夹具。状态矩阵见 [`PUBLICATION.md`](PUBLICATION.md)。

## 6. Branch and version policy / 分支与版本策略

- Daily work targets `develop`; release candidates are promoted to protected
  `main` through review.
- Versions use repository-scoped SemVer and immutable `v{version}` tags.
- A defective release requires a new patch version; published tags are not
  rewritten.

- 日常工作进入 `develop`；发布候选经审查提升到受保护的 `main`。
- 版本采用仓库范围的 SemVer，并使用不可变的 `v{version}` tag。
- 有缺陷的发布必须生成新的 patch 版本，不能重写已发布 tag。

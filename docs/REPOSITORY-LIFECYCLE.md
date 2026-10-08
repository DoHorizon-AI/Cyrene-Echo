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

The `Immutable component release` GitHub Actions workflow publishes attested
Echo component artifacts. The Azure definition remains a manual supplemental
lane for protected resources or private integration; it is not the automatic
CI authority. The Container Apps consumer updates the existing Echo app only
after verifying the exact source-SHA index, manifest, OCI digest, and GitHub
attestation.

`Immutable component release` GitHub Actions workflow 会发布带 attestation 的 Echo 组件制品。
Azure 定义仍用于受保护资源或私有集成的手动补充通道，不是自动 CI 权威。Container Apps
消费 workflow 只有在验证精确源码 SHA 对应的 index、manifest、OCI digest 与 GitHub attestation
后，才会更新已有 Echo app。

## 3.1 Immutable component delivery / 不可变组件交付

Successful component-release runs on `main` and `release` use the stable
channel; `develop` uses preview. The Azure workflow resolves the immutable
release for the triggering commit and refuses a missing or mismatched release.
Manual dispatch uses its current branch and commit under the same verification.
It does not build or push an image, use a mutable tag, or create an Azure app.
Existing Azure OIDC and Workspace-auth rollout gates, internal-ingress policy,
and healthy-revision/image verification remain in force.

`main` 和 `release` 上的成功组件发布运行使用 stable channel；`develop` 使用 preview。Azure
workflow 按触发提交查找不可变 release；release 缺失或不匹配时会拒绝部署。手动触发也会按当前
分支和提交执行相同验证。它不会构建或推送镜像、使用可变 tag 或创建 Azure app。现有 Azure
OIDC 与 Workspace-auth rollout 门禁、内网 ingress 策略，以及健康 revision/镜像验证均保持不变。

On 2026-10-08, both GitHub's default attestation bundle and the OCI-referrer
bundle verified the existing official Echo preview image digest
`sha256:3aa667dc3c8f7e2403ca6db55a4074443703fcf9b2fe6854911ae91485c9bb91`.
The statement subject name is `ghcr.io/dohorizon-ai/cyrene-echo`; `oci://` is
the `gh attestation verify` locator syntax, not part of the in-toto subject
name. The exact constrained verifier invocation was:

```bash
gh attestation verify \
  'oci://ghcr.io/dohorizon-ai/cyrene-echo@sha256:3aa667dc3c8f7e2403ca6db55a4074443703fcf9b2fe6854911ae91485c9bb91' \
  --repo DoHorizon-AI/Cyrene-Echo \
  --signer-workflow DoHorizon-AI/Cyrene-Echo/.github/workflows/component-release.yml \
  --source-ref refs/heads/develop \
  --source-digest 35d96fe6f16b77d589df74b072ecf9a4ed2fe359 \
  --predicate-type https://slsa.dev/provenance/v1 \
  --format json
```

Repeating that command with `--bundle-from-oci` also passed. The signed
statement binds the exact image digest to the Echo release workflow, `develop`,
and source commit `35d96fe6f16b77d589df74b072ecf9a4ed2fe359`. This records a
live verification of that already published image; it does not replace the
release workflow's validation of future image digests.

2026-10-08，当日使用 GitHub 默认 attestation bundle 和 OCI referrer bundle 两条路径，均通过
对现有官方 Echo preview 镜像摘要
`sha256:3aa667dc3c8f7e2403ca6db55a4074443703fcf9b2fe6854911ae91485c9bb91` 的验证。statement 的
subject name 是 `ghcr.io/dohorizon-ai/cyrene-echo`；`oci://` 仅用于 `gh attestation verify` 的
定位语法，不属于 in-toto subject name。上方完整命令约束了仓库、签名 workflow、源码 ref、源码摘要和
predicate；增加 `--bundle-from-oci` 后再次执行也通过。已签名 statement 将精确镜像摘要绑定到 Echo
release workflow、`develop` 和源码提交 `35d96fe6f16b77d589df74b072ecf9a4ed2fe359`。这是对已发布镜像
的实时验证记录，不能代替后续新镜像的发布验证。

The Linux OCI publication has a distinct Ubuntu 24.04 host manifest with
target `{os: linux, osVersion: 24.04, distribution: ubuntu,
distributionVersion: 24.04, architecture: x86_64, runtime: oci}`. Its image
platform remains Linux `amd64`; this is a host compatibility target, not a
Linux-native bundle. The Windows Docker Desktop manifest remains a separate
host target for the same signed image digest.

On Linux, the Plugins supervisor's direct `connection_ref` resolves to a
loopback gRPC endpoint. An OCI runtime that consumes this ref must use host
networking and inject the exact ref as
`CYRENE_EVALUATION_RUNNER_CONNECTION_REF`. Bind Echo itself to
`ECHO_HOST=127.0.0.1` and do not publish container ports; the image entrypoint's
default `0.0.0.0` bind is for a separately authenticated ingress deployment.
The Product keeps its database and artifacts in installer-owned persistent
paths at `/data/echo` and `/data/artifacts`. The verified container profile
used UID `10001`, dropped all Linux capabilities, mounted a read-only root
filesystem, and supplied a bounded `/tmp` tmpfs.

On 2026-10-08, a local Docker 29.8.0 smoke used the official image digest
`sha256:3aa667dc3c8f7e2403ca6db55a4074443703fcf9b2fe6854911ae91485c9bb91`
and a real Plugins exact-match endpoint returning a loopback `grpc://` ref.
With `--network host`, the Echo API completed an exact-match evaluation
(`201`, score `0.5`); without the ref, health remained `200` and evaluation
failed closed with `422 ECHO_EVALUATION_FAILED`. Removing and recreating the
container with the same data mount preserved the run and result. This proves
the Linux host-loopback transport and container data-mount behavior for that
published image. The local endpoint was started through the Plugins SDK, not
Platform supervision, and the smoke did not exercise Platform admission or
the installer uninstall transaction.

Linux OCI 发布会为 Ubuntu 24.04 主机生成独立 manifest，目标为
`{os: linux, osVersion: 24.04, distribution: ubuntu, distributionVersion: 24.04,
architecture: x86_64, runtime: oci}`。镜像平台仍是 Linux `amd64`；这是主机兼容目标，不是
Linux 原生 bundle。Windows Docker Desktop manifest 仍是同一签名镜像摘要对应的独立主机目标。

在 Linux 上，Plugins supervisor 的 direct `connection_ref` 指向 loopback gRPC endpoint。
消费该 ref 的 OCI runtime 必须使用 host networking，并把精确 ref 注入
`CYRENE_EVALUATION_RUNNER_CONNECTION_REF`。Echo 自身应绑定
`ECHO_HOST=127.0.0.1` 且不发布容器端口；镜像 entrypoint 的默认 `0.0.0.0` bind 仅用于另行配置
认证 ingress 的部署。Product 数据库与制品应放在 installer 管理的持久目录
`/data/echo` 和 `/data/artifacts`。已验证容器配置使用 UID `10001`、移除全部 Linux capabilities、
只读 root filesystem，并为 `/tmp` 提供有界 tmpfs。

2026-10-08，本地 Docker 29.8.0 使用官方镜像摘要
`sha256:3aa667dc3c8f7e2403ca6db55a4074443703fcf9b2fe6854911ae91485c9bb91` 和真实 Plugins
exact-match endpoint 运行 smoke；endpoint 由 Plugins SDK 返回 loopback `grpc://` ref。设置
`--network host` 后，Echo API 完成真实 exact-match 评估（`201`，score `0.5`）；缺少 ref 时 health
仍为 `200`，评估 fail-closed 并返回 `422 ECHO_EVALUATION_FAILED`。删除并重建容器、复用同一数据挂载后，
原 run 和 result 仍可读取。这证明该已发布镜像的 Linux host-loopback transport 与容器数据挂载行为。
本地 endpoint 由 Plugins SDK 启动，不是 Platform supervisor；该 smoke 没有验证 Platform admission 或
installer uninstall transaction。

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

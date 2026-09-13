# Dependency licenses and SBOM / 依赖许可证与 SBOM

This document is the source-level inventory for Echo's direct dependencies. It
is intentionally kept next to `pyproject.toml` and `uv.lock`; the lock file is
the authority for the complete transitive graph and exact artifact hashes.
This inventory does not relicense any dependency under Echo's Apache-2.0
license.

本文档是 Echo 直接依赖的源码级清单，和 `pyproject.toml`、`uv.lock` 放在一起维护；
锁文件是完整传递依赖图与精确 artifact hash 的权威来源。本文档不会把任何依赖默认为
Echo 的 Apache-2.0 许可证。

## First-party license / 一方许可证

Echo source, schemas, documentation, and examples are Apache-2.0. The
authoritative text is [`../LICENSE`](../LICENSE).

Echo 源码、schema、文档与示例采用 Apache-2.0，权威文本位于
[`../LICENSE`](../LICENSE)。

## Runtime dependencies / 运行时依赖

Versions below are pinned in the root `pyproject.toml` and resolved in
`uv.lock`.

以下版本在根目录 `pyproject.toml` 中锁定，并由 `uv.lock` 解析。

| Package / 包 | Version / 版本 | Source / 来源 | License status / 许可证状态 |
|---|---:|---|---|
| `fastapi` | 0.141.1 | PyPI | MIT |
| `httpx` | 0.28.1 | PyPI | BSD-3-Clause |
| `pydantic` | 2.13.5 | PyPI | MIT |
| `uvicorn` | 0.52.4 | PyPI | BSD-3-Clause |
| `cyrene-plugin-runtime` | 0.2.0 | Plugins git revision `3afbac4d386eb7a27f6778149187884820c0b7f6` | UNDECLARED upstream / 上游未声明 |

The Plugins runtime is a direct first-party dependency, but its package
metadata at the pinned revision does not declare a license field. It must be
given an explicit upstream license before an anonymous public clone can be
treated as release-ready.

Plugins runtime 是直接的一方依赖，但锁定 revision 的包元数据没有声明 license 字段。
在能够把匿名公开克隆视为可发布之前，必须先为它补充明确的上游许可证。

## Development dependencies / 开发依赖

These packages are used by the documented local checks and are not included
in Echo's runtime dependency set.

这些包用于文档化的本地检查，不属于 Echo 的运行时依赖集合。

| Package / 包 | Version / 版本 | License / 许可证 |
|---|---:|---|
| `cyrene-exact-match-evaluator` | 0.1.0, Plugins revision `3afbac4d386eb7a27f6778149187884820c0b7f6` | UNDECLARED upstream / 上游未声明 |
| `jsonschema` | 4.26.0 | MIT |
| `mypy` | 2.3.1 | MIT |
| `openapi-spec-validator` | 0.9.0 | Apache-2.0 |
| `pytest` | 9.1.1 | MIT |
| `ruff` | 0.16.5 | MIT |

The exact-match evaluator is a Plugins git dependency and also depends on the
Plugins runtime. Its upstream license metadata and anonymous-cloneability are
therefore release blockers, even though it is development-only.

exact-match evaluator 是 Plugins git 依赖，并且继续依赖 Plugins runtime。因此，即使它
仅用于开发，其上游许可证元数据与匿名克隆能力仍是公开发布阻塞项。

## Transitive dependencies / 传递依赖

`uv.lock` contains the complete resolved graph, including Starlette,
grpcio/protobuf overrides, `pydantic-core`, and validator support packages.
Do not maintain a second hand-written transitive list here. When the lock file
changes, regenerate the SBOM and review the resulting license metadata.

`uv.lock` 包含完整解析图，包括 Starlette、grpcio/protobuf override、`pydantic-core` 与
validator 支持包。不要在这里维护第二份手写的传递依赖清单。锁文件改变后，应重新生成
SBOM 并审查生成结果中的许可证元数据。

## SBOM entrypoint / SBOM 入口

With `uv` installed, generate a CycloneDX SBOM from the locked runtime and
development groups:

安装 `uv` 后，可从锁定的运行时与开发依赖组生成 CycloneDX SBOM：

```shell
sbom_dir="$(mktemp -d)"
uv export --frozen --all-groups --format cyclonedx1.5 \
  --output-file "$sbom_dir/cyrene-echo-python.cdx.json"
printf 'SBOM: %s\n' "$sbom_dir/cyrene-echo-python.cdx.json"
```

The output directory above is deliberately outside the repository. Review the
report for every `UNDECLARED` component before attaching it to a release. The
git-sourced Plugins packages need a public, immutable revision and explicit
license metadata before this report can be a complete public-release notice.

上述输出目录特意位于仓库外。发布前必须审查报告中的所有 `UNDECLARED` 组件。git 来源的
Plugins 包只有在 revision 公开且不可变、并补充明确许可证元数据后，才能构成完整的公开
发布声明。

The repository's `uv.lock` and the pinned source revision are the reproducible
inputs; no network-fetched package should be copied into this repository.

仓库的 `uv.lock` 与锁定的源码 revision 是可复现输入；不要把网络获取的依赖源码复制到本
仓库中。

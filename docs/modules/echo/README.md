# Echo module / Echo 模块

## Purpose / 目录用途

This module page describes Echo's current evaluation runtime and Product
contract surface. Echo owns evaluation-suite orchestration, runner profiles,
scoring, gate decisions, human annotation, and selected feedback exports.

本模块页说明 Echo 当前的评估运行时与产品契约范围。Echo 负责评估套件编排、运行器
配置档、评分、门禁决策、人工标注与选定反馈导出。

The runtime is implemented under `src/cyrene_echo/`; there is no
`legacy/navigator-feedback` tree in this checkout. The live Exchange judge and
live Catalyst handoff are `WIRED_NOT_RUN` without a reachable endpoint and
credential.

运行时实现位于 `src/cyrene_echo/`；当前检出中不存在 `legacy/navigator-feedback`
目录。没有可达端点与凭证时，真实 Exchange 判官与真实 Catalyst 交接保持
`WIRED_NOT_RUN`。

## Files and responsibilities / 文件与职责

| Path | Responsibility / 职责 |
|---|---|
| [`../../API.md`](../../API.md) | Evaluation objects, runner profiles, handoffs, and status matrix / 评估对象、运行器配置档、交接与状态矩阵 |
| [`../../REPOSITORY-LIFECYCLE.md`](../../REPOSITORY-LIFECYCLE.md) | Repository ownership, trust boundary, release topology, and branch model / 仓库归属、信任边界、发布拓扑与分支模型 |
| [`../../../README.md`](../../../README.md) | Repository entry point and authoritative-document links / 仓库入口与权威文档链接 |
| [`../../../service.json`](../../../service.json) | Service identity metadata / 服务身份元数据 |
| [`../../../repository-policy.yaml`](../../../repository-policy.yaml) | Repository lifecycle and governance metadata / 仓库生命周期与治理元数据 |
| [`../../../src/cyrene_echo/`](../../../src/cyrene_echo/) | Active runtime: API, service, engine profiles, store, and UI / 活跃运行时：API、服务、引擎配置档、存储与界面 |
| [`../../../contracts/product/v1/`](../../../contracts/product/v1/) | Product contract v1 and the local execution-port boundary / 产品契约 v1 与本地执行端口边界 |

## Suggested reading / 推荐阅读

1. `docs/architecture/overview.md` — understand evaluation stages and runner profiles.
2. `docs/API.md` — inspect the evaluation objects, bindings, and status matrix.
3. `contracts/product/v1/evaluation-execution-port.md` — understand the local runner seam.
4. `docs/REPOSITORY-LIFECYCLE.md` — understand release, trust, and ownership boundaries.

1. `docs/architecture/overview.md` —— 理解评估阶段与运行器配置档。
2. `docs/API.md` —— 查看评估对象、绑定与状态矩阵。
3. `contracts/product/v1/evaluation-execution-port.md` —— 理解本地运行器接缝。
4. `docs/REPOSITORY-LIFECYCLE.md` —— 理解发布、信任与职责边界。

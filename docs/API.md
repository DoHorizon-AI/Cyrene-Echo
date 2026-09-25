# Echo Product API & Evaluation Contract

This document describes the current Echo Product boundary. Echo owns
evaluation state and feedback selection. Its execution engines are replaceable
application ports behind explicit runner profiles, and its cross-product
handoffs use explicit Product APIs.

The status names in this document describe local implementation or wiring
evidence only. They do not claim hosted CI, live judge/Catalyst acceptance,
production security, or release publication. See [`PUBLICATION.md`](PUBLICATION.md).

本文状态名称只描述本地实现或接线证据，不代表 hosted CI、真实判官/Catalyst 验收、生产安全
或发布完成。详见 [`PUBLICATION.md`](PUBLICATION.md)。

## Ownership

Echo owns:

- `EvaluationSuite`, `EvaluationRun`, `EvaluationResult`, and `GateDecision`;
- per-sample evidence and `HumanAnnotation` records;
- `FeedbackSet` selection and immutable Catalyst-compatible exports;
- the replaceable `EvaluationExecutionPort`, its runner profiles, and the
  isolated Exchange judge adapter.

Echo does not own dataset curation or `DatasetVersion` state (Catalyst), model
training or model artifact production (Yield), model serving (Reactor), or
generic control-plane and Artifact Plane implementation (Platform). Echo
consumes but does not define `evaluation.runner.v1`; its contract and
exact-match implementation are owned by `Cyrene-Plugins-Official`.

`ArtifactRef` is a provider-neutral wire shape shared across Product handoffs.
It carries immutable content identity; its `kind` is an opaque producer-owned
string. Echo applies its own `dataset` check only where an evaluation input
requires a dataset. Echo consumes the pinned Platform artifact SDK for local
content-addressed storage without importing Platform business authority.

## Runner profiles

`engineBindingId` selects one declared runner binding. Binding ids remain
Echo-local names; `exact-match-plugin` maps to the resolved capability endpoint:

| Profile | Binding id | Evaluator | Acceptance class |
| --- | --- | --- | --- |
| `DIRECT_PLUGIN` | `exact-match-plugin` | `exact_match.v1` | `LOCAL_ENDPOINT_VERIFIED` |
| `PRODUCT_ADAPTER` | `exchange-judge` | `llm_judge.v1` | `WIRED_NOT_RUN` |

An undeclared binding fails closed with `ECHO_RUNNER_BINDING_UNKNOWN`; a
binding whose evaluator does not match the suite fails closed with
`ECHO_RUNNER_BINDING_MISMATCH` (both HTTP 422, before any runner executes).
Test doubles are `MOCK` and are never selectable runtime bindings.

## Implemented lifecycle

1. Import a session JSONL snapshot as an immutable `ArtifactRef`.
2. Create an `EvaluationSuite` with an exact-match or LLM-judge evaluator.
3. Execute the runner declared by the resolved binding and persist an
   `EvaluationRun`.
4. Persist immutable measurements, per-sample evidence, and a gate decision.
5. Record human annotations without changing model measurements.
6. Select and export a `FeedbackSet` as Catalyst-compatible JSONL.
7. Hand the resulting reference to Catalyst through its explicit Product
   handoff.

The run state is `RUNNING -> SUCCEEDED | FAILED | CANCELLED`. A poor score is
a successful run with a failing gate; execution failure is a failed run.

## Direct Product handoffs

Echo reads a source reference supplied by Navigator or another Product and
resolves the corresponding Artifact Plane reference locally. The selected
adapter sends typed records directly to the Plugin endpoint. Platform may
resolve its opaque `connection_ref`, but business payloads do not pass through
a Platform service.

Feedback export remains `PREPARED` until a caller explicitly sends the
reference to Catalyst through
`POST /api/v1/feedback-sets/{feedbackSetId}/actions/send-to-catalyst`. Without
a configured Catalyst URL the handoff fails closed with
`ECHO_CATALYST_NOT_CONNECTED`; an unreachable or unconfirmed target fails with
`ECHO_CATALYST_HANDOFF_FAILED` and the export stays `PREPARED`. Echo accepts
only Catalyst's HTTP 201 creation receipt with an exact preparation identity.
It then atomically stores that receipt, advances the export to `HANDLED_OFF`,
and replays it across process restarts without another downstream request.
Echo does not write Catalyst state or claim DatasetVersion publication.

The `ExchangeJudgePort` calls the configured Exchange OpenAI-compatible chat
endpoint directly. A live Exchange judge requires a bearer credential and a
reachable endpoint. Without both, real acceptance is `WIRED_NOT_RUN`; the
application fails closed with `ECHO_JUDGE_CREDENTIAL_UNAVAILABLE`. Transport
failures and HTTP rejections persist a `FAILED` run with
`ECHO_EVALUATION_FAILED`. Local HTTP test doubles prove adapter behavior only.

## Contract status

| Surface | Status | Evidence boundary |
| --- | --- | --- |
| Deterministic JSONL evaluation | `LOCAL_ENDPOINT_VERIFIED` | Plugins DirectPluginRuntime endpoint plus Echo adapter and Product tests |
| Evaluation state, results, gates, annotations | `REFERENCE_MVP_READY` | Product API and contract tests |
| Runner binding profiles | `REFERENCE_MVP_READY` | Declared bindings with fail-closed resolution tests |
| Catalyst feedback export | `REFERENCE_MVP_READY` | Explicit selection and immutable JSONL export tests |
| Exchange judge adapter | `WIRED_NOT_RUN` for real endpoint | Adapter tests use a local stdlib HTTP double |
| Catalyst handoff adapter | `LOCAL_ENDPOINT_VERIFIED` | Reachable HTTP target, strict owner receipt, fail-closed and restart replay tests |
| Live deployed Catalyst handoff | `WIRED_NOT_RUN` without a deployed target | Production connectivity and availability remain deployment evidence |
| Reusable runner contract | `DIRECT_RUNTIME_IMPLEMENTED` | Plugins-owned `evaluation.runner.v1`; production deployment remains separate |

The HTTP API is rooted at `/api/v1`, uses OpenAPI 3.1.2 and JSON Schema Draft
2020-12, and returns RFC 9457-compatible Product errors.
---
<!-- Chinese Translation / 中文翻译 -->

# Echo Product API 与评估契约

本文说明当前 Echo Product 边界。Echo 拥有评估状态和反馈选择。执行引擎通过显式 runner 配置实现为可替换的应用端口；跨 Product 交接使用明确的 Product API。

本文的状态名称只描述本地实现或接线证据，不代表 Hosted CI、在线 judge/Catalyst 验收、生产安全或发布完成。详见 [`PUBLICATION.md`](PUBLICATION.md)。

## 所有权

Echo 拥有：

- `EvaluationSuite`、`EvaluationRun`、`EvaluationResult` 和 `GateDecision`；
- 逐样本证据和 `HumanAnnotation` 记录；
- `FeedbackSet` 选择及不可变的 Catalyst 兼容导出；
- 可替换的 `EvaluationExecutionPort`、其 runner 配置和独立的 Exchange judge 适配器。

Echo 不拥有数据集策展或 `DatasetVersion` 状态（归 Catalyst）、模型训练或模型制品生产（归 Yield）、模型服务（归 Reactor），也不拥有通用控制面和 Artifact Plane 实现（归 Platform）。Echo 消费但不定义 `evaluation.runner.v1`；该契约及精确匹配实现由 `Cyrene-Plugins-Official` 所有。

`ArtifactRef` 是 Product 交接共享的 Provider 无关线格式。它携带不可变内容身份，其 `kind` 是不透明且由生产方拥有的字符串。仅当评估输入需要 Dataset 时，Echo 才执行自身的 `dataset` 类型检查。Echo 使用固定的 Platform artifact SDK 进行本地内容寻址存储，但不会导入 Platform 业务权威。

## Runner 配置

`engineBindingId` 选择一个已声明的 runner binding。Binding ID 保持为 Echo 本地名称；`exact-match-plugin` 映射到已解析的能力端点：

| 配置 | Binding ID | Evaluator | 验收类别 |
| --- | --- | --- | --- |
| `DIRECT_PLUGIN` | `exact-match-plugin` | `exact_match.v1` | `LOCAL_ENDPOINT_VERIFIED` |
| `PRODUCT_ADAPTER` | `exchange-judge` | `llm_judge.v1` | `WIRED_NOT_RUN` |

未声明的 binding 会以 `ECHO_RUNNER_BINDING_UNKNOWN` fail-closed；若 binding 的 evaluator 与 suite 不匹配，则以 `ECHO_RUNNER_BINDING_MISMATCH` fail-closed（两者均为 HTTP 422，且不会调用 runner）。测试替身属于 `MOCK`，永远不可选为运行时 binding。

## 已实现生命周期

1. 将会话 JSONL 快照作为不可变 `ArtifactRef` 导入。
2. 创建使用精确匹配或 LLM judge evaluator 的 `EvaluationSuite`。
3. 执行已解析 binding 声明的 runner，并持久化 `EvaluationRun`。
4. 持久化不可变测量值、逐样本证据和 gate 决策。
5. 记录人工标注，但不改变模型测量值。
6. 选择并将 `FeedbackSet` 导出为 Catalyst 兼容的 JSONL。
7. 通过 Catalyst 明确的 Product 交接接口传递导出引用。

Run 状态为 `RUNNING -> SUCCEEDED | FAILED | CANCELLED`。低分属于执行成功但 gate 失败；执行错误才属于失败的 run。

## Product 直连交接

Echo 读取 Navigator 或其他 Product 提供的来源引用，并在本地解析对应的 Artifact Plane 引用。所选适配器将类型化记录直接发送到 Plugin 端点。Platform 可以解析不透明的 `connection_ref`，但业务负载不会通过 Platform 服务。

反馈导出在调用方通过 `POST /api/v1/feedback-sets/{feedbackSetId}/actions/send-to-catalyst` 显式发送引用之前保持 `PREPARED`。未配置 Catalyst URL 时交接会以 `ECHO_CATALYST_NOT_CONNECTED` fail-closed；目标不可达或未确认时返回 `ECHO_CATALYST_HANDOFF_FAILED`，导出仍保持 `PREPARED`。Echo 只接受 HTTP 201 创建回执，且准备资源身份必须完全匹配。随后 Echo 会原子保存回执、将导出状态推进为 `HANDLED_OFF`，并在进程重启后重放回执，不会再次请求下游。Echo 不写入 Catalyst 状态，也不声称 DatasetVersion 已发布。

`ExchangeJudgePort` 直接调用配置的 Exchange OpenAI 兼容 Chat 端点。在线 Exchange judge 需要 Bearer 凭据和可访问端点。缺少任一条件时，真实验收状态为 `WIRED_NOT_RUN`，应用以 `ECHO_JUDGE_CREDENTIAL_UNAVAILABLE` fail-closed。传输失败和 HTTP 拒绝会将 run 持久化为 `FAILED`，并使用 `ECHO_EVALUATION_FAILED`。本地 HTTP 测试替身只证明适配器行为。

## 契约状态

| 表面 | 状态 | 证据边界 |
| --- | --- | --- |
| 确定性 JSONL 评估 | `LOCAL_ENDPOINT_VERIFIED` | Plugins DirectPluginRuntime 端点、Echo 适配器和 Product 测试 |
| 评估状态、结果、gate 和标注 | `REFERENCE_MVP_READY` | Product API 与契约测试 |
| Runner binding 配置 | `REFERENCE_MVP_READY` | 已声明 binding 及 fail-closed 解析测试 |
| Catalyst 反馈导出 | `REFERENCE_MVP_READY` | 显式选择和不可变 JSONL 导出测试 |
| Exchange judge 适配器 | 真实端点为 `WIRED_NOT_RUN` | 适配器测试使用本地标准库 HTTP 替身 |
| Catalyst 交接适配器 | `LOCAL_ENDPOINT_VERIFIED` | 可访问 HTTP 目标、严格 owner 回执、fail-closed 和重启重放测试 |
| 已部署 Catalyst 的在线交接 | 无已部署目标时为 `WIRED_NOT_RUN` | 生产连通性和可用性仍需部署证据 |
| 可复用 runner 契约 | `DIRECT_RUNTIME_IMPLEMENTED` | Plugins 所有的 `evaluation.runner.v1`；生产部署另行验收 |

HTTP API 根路径为 `/api/v1`，使用 OpenAPI 3.1.2 和 JSON Schema Draft 2020-12，并返回兼容 RFC 9457 的 Product 错误。

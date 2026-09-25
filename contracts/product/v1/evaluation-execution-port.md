# Echo local evaluation-execution port

`EvaluationExecutionPort` is an internal Echo application boundary. It receives
an Artifact Plane-resolved private path and an Echo `EvaluationSuite`, then
returns measurements, per-sample evidence, and a staged report. The
`DirectPluginEvaluationPort` adapter reads the Product-owned artifact and calls
the Plugins-owned `evaluation.runner.v1` typed endpoint. Echo does not define
that capability or proxy its business payload through Platform.

The port cannot decide gate policy, assign Product lifecycle state, publish
Product events, select provider packages, or own Artifact Plane bytes. Echo's
service persists the returned evidence and makes the gate decision.

## Runner profiles and bindings

Echo owns the runner profile vocabulary; the direct Plugin profile identifies
how a selected implementation is connected, not a second capability contract:

| Profile | Binding id | Implementation | Acceptance class |
| --- | --- | --- | --- |
| `DIRECT_PLUGIN` | `exact-match-plugin` | `DirectPluginEvaluationPort` → `evaluation.runner.v1` | `LOCAL_ENDPOINT_VERIFIED` |
| `PRODUCT_ADAPTER` | `exchange-judge` | `ExchangeJudgePort` | `WIRED_NOT_RUN` |

- `LOCAL_ENDPOINT_VERIFIED` means the Product adapter and Plugins implementation
  passed a real local DirectPluginRuntime endpoint test; it is not a production
  deployment claim.
- `WIRED_NOT_RUN` means the remote judge is wired through an explicit adapter
  (`llm_judge.v1` suites) but has no live acceptance without a reachable
  Exchange endpoint plus bearer credential.
- `MOCK` is reserved for test doubles. Mocks are never selectable runtime
  bindings and must not appear in `cyrene_echo.engine.RUNNER_BINDINGS`.

An `engineBindingId` must resolve to a declared binding whose evaluator matches
the suite evaluator; otherwise the run fails closed with
`ECHO_RUNNER_BINDING_UNKNOWN` or `ECHO_RUNNER_BINDING_MISMATCH` (HTTP 422) and
no runner is invoked.

## Implementations and adapters

- `evaluation.runner.v1` exact-match scoring is implemented only by
  `Cyrene-Plugins-Official/plugins/evaluation/exact-match`.
- `DirectPluginEvaluationPort` reads Echo-owned JSONL, invokes the typed direct
  endpoint, validates the response, and writes the staged report. Missing or
  invalid `CYRENE_EVALUATION_RUNNER_CONNECTION_REF` fails closed; there is no
  in-Product scorer fallback.
- `ExchangeJudgePort` is an isolated adapter that calls the configured Exchange
  endpoint at `/v1/chat/completions` with a bearer token. Missing credentials or
  endpoint reachability keep live acceptance at `WIRED_NOT_RUN` and fail closed
  with `ECHO_JUDGE_CREDENTIAL_UNAVAILABLE`; no score is fabricated. Transport
  failures and HTTP rejections persist a `FAILED` run with
  `ECHO_EVALUATION_FAILED`.

Tests exercise the Exchange adapter against a local stdlib HTTP test double.
Provider usage is carried only when returned by the provider; missing usage is
recorded as `null`.
---
<!-- Chinese Translation / 中文翻译 -->

# Echo 本地评估执行端口

`EvaluationExecutionPort` 是 Echo 内部的应用边界。它接收 Artifact Plane 解析出的私有路径和 Echo `EvaluationSuite`，然后返回测量值、逐样本证据及暂存报告。`DirectPluginEvaluationPort` 适配器读取 Product 所有的制品，并调用 Plugins 所有的类型化 `evaluation.runner.v1` 端点。Echo 不定义此能力，也不通过 Platform 代理其业务负载。

此端口不能决定 gate 策略、分配 Product 生命周期状态、发布 Product 事件、选择 Provider 包，也不拥有 Artifact Plane 字节。Echo service 持久化返回的证据并作出 gate 决策。

## Runner 配置与 binding

Echo 拥有 runner 配置词汇。直连 Plugin 配置只标识如何连接选定实现，并不是第二份能力契约：

| 配置 | Binding ID | 实现 | 验收类别 |
| --- | --- | --- | --- |
| `DIRECT_PLUGIN` | `exact-match-plugin` | `DirectPluginEvaluationPort` -> `evaluation.runner.v1` | `LOCAL_ENDPOINT_VERIFIED` |
| `PRODUCT_ADAPTER` | `exchange-judge` | `ExchangeJudgePort` | `WIRED_NOT_RUN` |

- `LOCAL_ENDPOINT_VERIFIED` 表示 Product 适配器和 Plugins 实现已通过真实本地 DirectPluginRuntime 端点测试；这不代表生产部署已验收。
- `WIRED_NOT_RUN` 表示远端 judge 已通过显式适配器接通（供 `llm_judge.v1` suite 使用），但没有可访问的 Exchange 端点和 Bearer 凭据就不能进行在线验收。
- `MOCK` 只保留给测试替身。Mock 不能作为可选择的运行时 binding，也不得出现在 `cyrene_echo.engine.RUNNER_BINDINGS` 中。

`engineBindingId` 必须解析为已声明且 evaluator 与 suite 匹配的 binding；否则 run 会以 fail-closed 失败，返回 `ECHO_RUNNER_BINDING_UNKNOWN` 或 `ECHO_RUNNER_BINDING_MISMATCH`（HTTP 422），且不会调用 runner。

## 实现与适配器

- `evaluation.runner.v1` 精确匹配评分只在 `Cyrene-Plugins-Official/plugins/evaluation/exact-match` 中实现。
- `DirectPluginEvaluationPort` 读取 Echo 所有的 JSONL，调用类型化直连接口，校验响应并写入暂存报告。`CYRENE_EVALUATION_RUNNER_CONNECTION_REF` 缺失或无效时按 fail-closed 处理；Product 内没有评分器回退。
- `ExchangeJudgePort` 是独立适配器，使用 Bearer token 调用配置的 Exchange `/v1/chat/completions` 端点。凭据缺失或端点不可达时，在线验收保持 `WIRED_NOT_RUN`，并以 `ECHO_JUDGE_CREDENTIAL_UNAVAILABLE` fail-closed；不会伪造评分。传输失败和 HTTP 拒绝会将 run 持久化为 `FAILED`，并使用 `ECHO_EVALUATION_FAILED`。

测试通过本地标准库 HTTP 替身覆盖 Exchange 适配器。仅当 Provider 返回 usage 时才会携带该值；缺失时记录为 `null`。

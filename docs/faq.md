# FAQ and troubleshooting / 常见问题与排障

## Is Echo runnable today? / Echo 现在可以运行吗？

Yes. `src/cyrene_echo/` is the active runtime: a FastAPI Product service backed
by SQLite and a local content-addressed Artifact Plane. Run `uv run pytest` for
the acceptance suites and start the service with the `cyrene-echo` console
script. Evaluation state, gates, annotations, and feedback export are real and
tested. Exact-match execution additionally requires the Plugins-owned
`evaluation.runner.v1` endpoint in `CYRENE_EVALUATION_RUNNER_CONNECTION_REF`;
without it Echo fails closed. The live Exchange judge and Catalyst handoff stay
`WIRED_NOT_RUN` until their endpoint and credential are configured.

可以运行。`src/cyrene_echo/` 是活跃运行时：由 SQLite 与本地内容寻址制品平面支撑的
FastAPI 产品服务。`uv run pytest` 运行验收套件，`cyrene-echo` 启动服务。评估状态、
门禁、标注与反馈导出均有真实测试。exact-match 还要求通过
`CYRENE_EVALUATION_RUNNER_CONNECTION_REF` 配置 Plugins 所有的
`evaluation.runner.v1` 端点；缺失时 Echo fail closed。Exchange 判官与 Catalyst
交接在没有可达端点与凭证时保持 `WIRED_NOT_RUN`。

## Where is the active source? / 活跃源码在哪里？

The active source is `src/cyrene_echo/` with tests under `tests/` and Product
contracts under `contracts/product/v1/`. There is no `legacy/navigator-feedback`
tree in this checkout.

活跃源码位于 `src/cyrene_echo/`，测试在 `tests/`，产品契约在 `contracts/product/v1/`。
当前检出中不存在 `legacy/navigator-feedback` 目录。

## Which file defines capability names? / 哪个文件定义能力名称？

Echo does not define capability contracts. `evaluation.runner.v1` is declared
and implemented in `Cyrene-Plugins-Official`; Echo maps its local
`exact-match-plugin` binding to that endpoint. `service.json` remains only the
Echo service-identity manifest. See `docs/API.md` and the execution-port contract.

Echo 不定义 capability 契约。`evaluation.runner.v1` 由
`Cyrene-Plugins-Official` 声明并实现；Echo 将本地 `exact-match-plugin` 绑定映射到
该端点。`service.json` 仍仅是 Echo 服务身份清单。

## Can Echo evaluate any model endpoint? / Echo 可以评估任意模型端点吗？

Evaluation runs consume an immutable input artifact; the judge profile selects
the Exchange endpoint that produces completion scores. Yield checkpoints and
Reactor live endpoints are distinct target authorities, and the current MVP
does not fetch them directly: a session snapshot must be imported as an
artifact first.

评估运行消费不可变输入制品；判官配置选择产出评分所需的 Exchange 端点。Yield 检查点
与 Reactor 在线端点属于不同目标权威，当前 MVP 不直接抓取其内容：会话快照需先作为
制品导入。

## What does an `engineBindingId` actually do? / `engineBindingId` 到底做什么？

It selects one declared runner binding, for example `exact-match-plugin`
(`DIRECT_PLUGIN`, `LOCAL_ENDPOINT_VERIFIED`) for `exact_match.v1` suites or
`exchange-judge` (`PRODUCT_ADAPTER`, `WIRED_NOT_RUN`) for `llm_judge.v1` suites.
An undeclared binding returns `ECHO_RUNNER_BINDING_UNKNOWN`; a binding that
does not match the suite evaluator returns `ECHO_RUNNER_BINDING_MISMATCH`.
There is no silent default runner.

它选择一条已声明的运行器绑定，例如 `exact_match.v1` 套件使用
`exact-match-plugin`（`DIRECT_PLUGIN`、`LOCAL_ENDPOINT_VERIFIED`），`llm_judge.v1` 套件使用
`exchange-judge`（`PRODUCT_ADAPTER`、`WIRED_NOT_RUN`）。未声明的绑定返回
`ECHO_RUNNER_BINDING_UNKNOWN`；与套件评估器不匹配的绑定返回
`ECHO_RUNNER_BINDING_MISMATCH`。不存在静默默认运行器。

## What should not be added to Echo? / Echo 不应加入什么？

Do not add training loops, model serving, raw dataset ingestion, or generic
process isolation. Those responsibilities belong to Yield, Reactor, Catalyst,
and Platform Kernel respectively. Do not add a second runner or judge runtime
outside the declared profiles, and do not give Echo cross-Product state
authority.

不要在 Echo 中加入训练循环、模型服务、原始数据摄取或通用进程隔离；这些职责分别归属
于 Yield、Reactor、Catalyst 与 Platform Kernel。不要在已声明配置档之外新增第二套
运行器或判官运行时，也不要让 Echo 持有跨产品状态权威。

## How should an evaluation failure be isolated? / 如何定位评估失败？

Check layers in order: request validation, suite and runner binding resolution,
judge credentials, target invocation, metric computation, and report
persistence. Keep target/provider failures separate from scoring-policy
failures: a transport failure persists a `FAILED` run (`ECHO_EVALUATION_FAILED`),
while a poor score is a `SUCCEEDED` run with a `FAIL` gate.

按以下层次排查：请求校验、套件与运行器绑定解析、判官凭证、目标调用、指标计算、报告
持久化。将目标/提供方失败与评分策略失败分开：传输失败持久化为 `FAILED` 运行
（`ECHO_EVALUATION_FAILED`），而低分是 `SUCCEEDED` 运行加上 `FAIL` 门禁。

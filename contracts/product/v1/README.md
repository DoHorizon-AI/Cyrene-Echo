# Echo Product contract v1

Status: `LOCAL_ENDPOINT_VERIFIED`; the Plugins-owned deterministic evaluator,
Echo Product lifecycle, direct adapter, and local Artifact Plane adapter are
implemented. Production deployment and a live Exchange judge remain separate.

Echo owns `EvaluationSuite`, `EvaluationRun`, `EvaluationResult`,
`GateDecision`, `JudgeProfile`, `SampleRecord`, `HumanAnnotation`, and
`FeedbackSet`. An evaluation engine produces measurements, per-sample
evidence, and report bytes; it does not decide Product lifecycle state or
make a GateDecision authoritative. Human annotations are recorded alongside
the model score and never overwrite it.

## What this MVP delivers

- Deterministic scoring via `exact_match.v1` over session JSONL records.
- Per-sample results preserving the evaluated model/endpoint, input version
  (`inputDigest`), scoring config (the suite), scorer or judge identity, and
  the raw output. Usage facts are carried only when the provider reported
  them; missing usage is never estimated.
- Human review: manual score, corrected output, and preference over each
  sample, kept distinct from the model score.
- `FeedbackSet` built only from explicitly user-selected sample indexes;
  held-out evaluation samples are never auto-exported as training data.
- Catalyst-compatible JSONL export (`instruction` / `output` / `input` +
  provenance) published as a dataset `ArtifactRef`. Echo declares
  `handoffStatus = PREPARED` until the explicit Catalyst action returns a
  verified preparation receipt, then persists `HANDLED_OFF`.
- Isolated `ExchangeJudgePort` adapter that calls Exchange through the
  OpenAI-compatible `/v1/chat/completions` endpoint. Real judge acceptance is
  recorded as `WIRED_NOT_RUN` when credentials or an endpoint are unavailable;
  tests exercise this port against a local stdlib HTTP test double, never a
  real model endpoint.

## State and authority

- `EvaluationSuite`: `ACTIVE -> ARCHIVED`. `evaluator` is
  `exact_match.v1` or `llm_judge.v1`; an `llm_judge.v1` suite references a
  `JudgeProfile`.
- `EvaluationRun`: `RUNNING -> SUCCEEDED | FAILED | CANCELLED`.
- `GateDecision`: immutable `PASS | FAIL | ERROR` evidence.
- A `FAIL` gate is a successful evaluation whose policy threshold was not met.
  It is never rewritten to a failed run.
- `SampleRecord`: immutable per-sample evidence anchored to one run.
- `HumanAnnotation`: idempotent per `(runId, sampleIndex, reviewer)`; updating
  it does not mutate the `SampleRecord`.
- `FeedbackSet`: `OPEN -> EXPORTED`. `handoffStatus` is `PREPARED` until an
  external consumer (Catalyst) confirms the export, then `HANDLED_OFF`.
  Failed or malformed acknowledgements never advance the status.
- Artifact bytes remain in the Artifact Plane. Echo persists input/report
  `ArtifactRef` values and their Product-visible provenance.
- The reference adapter resolves provider-neutral `ArtifactRef` values inside
  its Echo-owned local Artifact Plane. Filesystem locations never cross the
  Product API.
- `engineBindingId` identifies the selected Echo execution adapter.
  `DirectPluginEvaluationPort` consumes the Plugins-owned
  `evaluation.runner.v1` contract using an opaque `connection_ref`.
- Events are notifications derived from committed resources, not the source of
  truth.

The Product application boundary and external capability handoff are documented
in `evaluation-execution-port.md`.

## Notifications

After durable commits, Echo may publish created/updated notifications for
`evaluation-suite` and `evaluation-run`, plus created notifications for
`evaluation-result`, `gate-decision`, `sample-record`, `human-annotation`,
and `feedback-set`, using types such as
`dev.cyrene.echo.evaluation-run.updated.v1`. The common Product event envelope
contains resource URI/version and change kind only. Consumers re-read Echo and
tolerate duplicates, reordering, and newer versions. The synchronous MVP does
not claim a durable outbox publisher.

## Compatibility

The API root is `/api/v1` and consumes the Workspace `product-http-v1`
compatibility profile, including deprecation and removal policy. OpenAPI is
pinned to 3.1.2, JSON Schema to Draft 2020-12, and errors to RFC 9457 with
stable Cyrene extensions.

`Idempotency-Key` has Cyrene semantics: a request replays the current state of
the same Product resource, including a run whose first attempt failed, while a
different canonical body with the same key returns `ECHO_IDEMPOTENCY_CONFLICT`.

The exact-match engine runs only in Plugins and has real local endpoint
coverage. Echo has no local scoring fallback. The Exchange judge adapter is
wired but live judge acceptance is `WIRED_NOT_RUN` without credentials.

## Catalyst handoff contract

Echo exports a `FeedbackSet` as a JSONL `ArtifactRef` of kind `dataset`. Each
line is a `TrainingCandidateRow` with `instruction`, `output`, `input`, an
optional `rejectedOutput` for preference pairs, and provenance
(`sourceRunId`, `sourceSampleIndex`, `sourceKind`, `evaluator`, `modelRef`,
`annotatedBy`). Catalyst ingests the same `ArtifactRef` shape via its
`FeedbackImportRequest`; the Catalyst `MappingConfig` consumes
`instruction`/`output`/`input` and ignores provenance fields. Echo requires an
HTTP 201 receipt whose target is exactly
`cyrene://catalyst/preparations/{id}`, persists it atomically with the
`HANDLED_OFF` transition, and returns that receipt on identical retries after
restart. Missing Catalyst fields should be requested explicitly rather than
reinventing a global protocol.
---
<!-- Chinese Translation / 中文翻译 -->

# Echo Product 契约 v1

状态为 `LOCAL_ENDPOINT_VERIFIED`：Plugins 所有的确定性评估器、Echo Product 生命周期、直连适配器和本地 Artifact Plane 适配器均已实现。生产部署和在线 Exchange judge 属于独立验收项。

Echo 拥有 `EvaluationSuite`、`EvaluationRun`、`EvaluationResult`、`GateDecision`、`JudgeProfile`、`SampleRecord`、`HumanAnnotation` 和 `FeedbackSet`。评估引擎生成测量值、逐样本证据和报告字节，但不决定 Product 生命周期状态，也不使 GateDecision 成为权威。人工标注与模型评分并列记录，绝不覆盖模型评分。

## MVP 提供的能力

- 对会话 JSONL 记录使用 `exact_match.v1` 执行确定性评分。
- 逐样本结果保留被评估模型/端点、输入版本（`inputDigest`）、评分配置（所属 suite）、评分器或 judge 身份以及原始输出。只有 Provider 实际报告时才携带用量事实；缺失用量绝不估算。
- 人工审核：逐样本记录人工评分、修正输出和偏好，并与模型评分分开保存。
- `FeedbackSet` 只使用用户显式选择的样本索引构建；留出的评估样本不会自动导出为训练数据。
- Catalyst 兼容的 JSONL 导出（`instruction` / `output` / `input` 及来源信息）会作为 `dataset` 类型的 `ArtifactRef` 发布。显式 Catalyst 操作返回经过验证的 preparation 回执之前，Echo 将 `handoffStatus` 设为 `PREPARED`；收到回执后才持久化为 `HANDLED_OFF`。
- 独立的 `ExchangeJudgePort` 通过 OpenAI 兼容的 `/v1/chat/completions` 端点调用 Exchange。凭据或端点不可用时，真实 judge 验收状态记为 `WIRED_NOT_RUN`；测试通过本地标准库 HTTP 替身覆盖此端口，不调用真实模型端点。

## 状态与权威

- `EvaluationSuite`：`ACTIVE -> ARCHIVED`。`evaluator` 为 `exact_match.v1` 或 `llm_judge.v1`；后者必须引用 `JudgeProfile`。
- `EvaluationRun`：`RUNNING -> SUCCEEDED | FAILED | CANCELLED`。
- `GateDecision`：不可变的 `PASS | FAIL | ERROR` 证据。
- `FAIL` gate 表示评估成功但未达到策略阈值，不能改写为失败的 run。
- `SampleRecord`：锚定到一个 run 的不可变逐样本证据。
- `HumanAnnotation`：按 `(runId, sampleIndex, reviewer)` 幂等；更新标注不会修改 `SampleRecord`。
- `FeedbackSet`：`OPEN -> EXPORTED`。外部消费者 Catalyst 确认导出之前，`handoffStatus` 为 `PREPARED`；确认后为 `HANDLED_OFF`。失败或格式错误的确认不会推进状态。
- Artifact 字节留在 Artifact Plane。Echo 持久化输入/报告 `ArtifactRef` 及 Product 可见的来源信息。
- 参考适配器在 Echo 所有的本地 Artifact Plane 内解析 Provider 无关的 `ArtifactRef`；文件系统位置不会穿过 Product API。
- `engineBindingId` 标识选定的 Echo 执行适配器。`DirectPluginEvaluationPort` 使用不透明的 `connection_ref` 调用 Plugins 所有的 `evaluation.runner.v1` 契约。
- 事件是从已提交资源派生的通知，不是真相来源。

Product 应用边界和外部能力交接见 `evaluation-execution-port.md`。

## 通知

持久化提交后，Echo 可以为 `evaluation-suite` 和 `evaluation-run` 发布创建/更新通知，并为 `evaluation-result`、`gate-decision`、`sample-record`、`human-annotation` 和 `feedback-set` 发布创建通知；类型示例为 `dev.cyrene.echo.evaluation-run.updated.v1`。通用 Product 事件信封只包含资源 URI/版本和变更类型。消费者需重新读取 Echo，并容忍重复、乱序和更新版本。同步 MVP 不宣称提供持久化 outbox 发布器。

## 兼容性

API 根路径为 `/api/v1`，使用 Workspace 的 `product-http-v1` 兼容配置文件，包括弃用和移除策略。OpenAPI 固定为 3.1.2，JSON Schema 为 Draft 2020-12，错误使用带稳定 Cyrene 扩展的 RFC 9457 格式。

`Idempotency-Key` 遵循 Cyrene 语义：重放请求会返回同一 Product 资源的当前状态，包括首次尝试失败的 run；相同 key 配合不同的规范请求体会返回 `ECHO_IDEMPOTENCY_CONFLICT`。

精确匹配引擎只在 Plugins 中运行，并已获得真实本地端点覆盖。Echo 没有本地评分回退。未提供凭据时，Exchange judge 适配器虽已接通，但在线验收仍为 `WIRED_NOT_RUN`。

## Catalyst 交接契约

Echo 将 `FeedbackSet` 导出为 kind 为 `dataset` 的 JSONL `ArtifactRef`。每行是一个 `TrainingCandidateRow`，包含 `instruction`、`output`、`input`、偏好样本对可选的 `rejectedOutput`，以及来源信息（`sourceRunId`、`sourceSampleIndex`、`sourceKind`、`evaluator`、`modelRef`、`annotatedBy`）。Catalyst 通过 `FeedbackImportRequest` 接收相同的 `ArtifactRef` 形状；Catalyst 的 `MappingConfig` 使用 `instruction`/`output`/`input`，忽略来源字段。Echo 要求 HTTP 201 回执，且目标必须精确为 `cyrene://catalyst/preparations/{id}`；它会将回执与 `HANDLED_OFF` 状态转换原子持久化，并在重启后对相同重试返回该回执。若 Catalyst 缺少字段，应显式提出请求，不要另造全局协议。

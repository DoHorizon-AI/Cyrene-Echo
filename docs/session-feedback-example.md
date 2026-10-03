# Echo session-feedback example

This document describes a complete, real-executed example of the Echo
session-evaluation and feedback path, from session JSONL to a
human-confirmed Catalyst training candidate. It states exactly which parts
were executed for real and which remain `NOT_RUN`.

## User path

1. Import or select a set of session/model outputs.
2. Select an existing or new minimal evaluation method (`EvaluationSuite`).
3. Execute the evaluation (`EvaluationRun`).
4. View per-sample results and the summary (`SampleRecord` + `EvaluationResult` + `GateDecision`).
5. Manually score, correct, and filter.
6. Export a `FeedbackSet` of training candidates.
7. Hand the export to Catalyst.

## Real-executed deterministic path

This path is covered by `tests/test_session_feedback.py` and runs against a
real SQLite store and a real filesystem Artifact Plane. No real model endpoint
is required.

```bash
# From the repository root:
uv run pytest -q tests/test_session_feedback.py::test_session_to_feedback_export_deterministic
```

### 1. Import sessions

`POST /api/v1/session-artifacts` with `application/jsonl` body
(`examples/session_feedback_demo.jsonl`). Echo publishes the bytes as a
content-addressed dataset `ArtifactRef` (`artifact://sha256/<digest>`).

### 2. Create an evaluation method

```bash
POST /api/v1/evaluation-suites
{"name":"session-exact","evaluator":"exact_match.v1",
 "expectedField":"expected","actualField":"actual","threshold":0.7}
```

### 3. Execute the evaluation

```bash
POST /api/v1/evaluation-runs
{"suiteId":"<suite>","inputArtifact":"<artifact>","engineBindingId":"exact-match-plugin"}
```

The run transitions `RUNNING -> SUCCEEDED`. `DirectPluginEvaluationPort` sends
the records to the Plugins-owned `evaluation.runner.v1` exact-match endpoint,
validates its measurements, and writes a staged report. Echo persists
`EvaluationResult`, `GateDecision`, and one `SampleRecord` per input record.

### 4. Per-sample results and summary

```bash
GET /api/v1/evaluation-runs/{runId}/samples
GET /api/v1/evaluation-results/{resultId}
GET /api/v1/gate-decisions/{gateId}
```

Each `SampleRecord` preserves the evaluated `modelRef`, `endpointRef`, the
input version (`inputDigest`), the evaluator/judge identity, the raw output,
and provider `usage` when the record carried it. A record without usage has
`usage: null`; Echo never estimates it.

### 5. Distinguish outcomes

| Case | How it appears |
|---|---|
| Evaluation execution failure | `EvaluationRun.state = FAILED` with `failure.code = ECHO_EVALUATION_FAILED` (HTTP 422). |
| Evaluation success but poor score | `EvaluationRun.state = SUCCEEDED`, `GateDecision.outcome = FAIL`. A `FAIL` gate is never rewritten as a failed run. |
| Model did not provide Usage | `SampleRecord.usage = null`. |
| Human opinion vs model score | `SampleRecord.score`/`passed` are unchanged by annotation; `HumanAnnotation.manualScore`/`preference` are stored separately. |

### 6. Human review

```bash
POST /api/v1/evaluation-runs/{runId}/annotations
{"sampleIndex":2,"reviewer":"qa","manualScore":0.0,
 "correctedOutput":"北京","preference":"prefer_corrected","note":"wrong capital"}
GET  /api/v1/evaluation-runs/{runId}/annotations
GET  /api/v1/evaluation-runs/{runId}/samples?only_passed=false
```

### 7. Export a FeedbackSet

```bash
POST /api/v1/feedback-sets
{"name":"demo-feedback","runId":"<run>","sampleIndexes":[2],"annotationIds":["<annotation>"]}
POST /api/v1/feedback-sets/{feedbackSetId}/export
GET  /api/v1/feedback-sets/{feedbackSetId}/export   # downloads Catalyst-compatible JSONL
```

The export is a JSONL dataset `ArtifactRef` of `TrainingCandidateRow` lines:

```json
{"instruction":"中国首都是哪里?","output":"北京","input":"",
 "rejectedOutput":"上海","sourceRunId":"<run>","sourceSampleIndex":2,
 "sourceKind":"preference","evaluator":"exact_match.v1",
 "modelRef":"qwen-demo","annotatedBy":"qa"}
```

`handoffStatus = PREPARED`. Exporting never auto-delivers: a caller either
hands the `ArtifactRef` to Catalyst manually or invokes the explicit direct
handoff `POST /api/v1/feedback-sets/{feedbackSetId}/actions/send-to-catalyst`.
The handoff stays `PREPARED` until Catalyst confirms the target; unreachable or
unconfirmed targets fail closed (`ECHO_CATALYST_NOT_CONNECTED`,
`ECHO_CATALYST_HANDOFF_FAILED`). A valid HTTP 201 preparation receipt advances
the FeedbackSet to `HANDLED_OFF` and is stored for idempotent replay, including
after an Echo restart. Held-out samples (those not in `sampleIndexes`) are
never exported.

## Model-judge path (`WIRED_NOT_RUN` against a real endpoint)

The LLM-judge evaluator is wired through the isolated `ExchangeJudgePort`,
which calls an Exchange endpoint at `/v1/chat/completions` with a bearer
token. Real acceptance against a live Exchange + real judge model is
`WIRED_NOT_RUN` in this MVP because no model credentials or live endpoint are
available.

The path is exercised by tests against a local stdlib HTTP test double
(`tests/test_session_feedback.py::test_exchange_judge_adapter_records_usage_and_judge_identity`
and `test_exchange_judge_without_usage_records_none`). That double is a test
fixture, not a real judge; results from it are never claimed as real judge
acceptance. Without a configured bearer token, a judge run fails fast with
`ECHO_JUDGE_CREDENTIAL_UNAVAILABLE` (HTTP 503) and the run is recorded as
`FAILED` (`test_real_judge_without_credential_is_wired_not_run`). This is a fail-closed
wired path, not live judge acceptance.

## What was real vs NOT_RUN

| Surface | Status |
|---|---|
| Deterministic exact-match evaluation | Real, tested. |
| Per-sample results, human annotation, filtering | Real, tested. |
| FeedbackSet export (Catalyst-compatible JSONL) | Real, tested. |
| Honest handoff (`PREPARED -> HANDLED_OFF`) | Real, tested against a reachable local HTTP target. |
| Exchange judge adapter wiring + test-double | Real, tested (test double only). |
| Real judge acceptance (live Exchange + real model) | `WIRED_NOT_RUN`. |
| Explicit Catalyst handoff (`actions/send-to-catalyst`) | Adapter, receipt validation, persistence, and restart replay are tested locally; deployed Catalyst acceptance remains `WIRED_NOT_RUN`. |
| Catalyst ingestion of the exported `ArtifactRef` | Owner-confirmed receipt is required; Echo does not write Catalyst state or claim publication. |
---
<!-- Chinese Translation / 中文翻译 -->

# Echo 会话反馈示例

本文描述一条完整且真实执行过的 Echo 会话评估与反馈路径，从会话 JSONL 到人工确认的 Catalyst 训练候选。文中明确区分真实执行的部分和仍为 `NOT_RUN` 的部分。

## 用户操作路径

1. 导入或选择一组会话/模型输出。
2. 选择现有或新建的最小评估方法（`EvaluationSuite`）。
3. 执行评估（`EvaluationRun`）。
4. 查看逐样本结果和摘要（`SampleRecord`、`EvaluationResult`、`GateDecision`）。
5. 手动评分、修正并筛选。
6. 导出训练候选 `FeedbackSet`。
7. 将导出结果交给 Catalyst。

## 真实执行的确定性路径

该路径由 `tests/test_session_feedback.py` 覆盖，并使用真实 SQLite 存储和真实文件系统 Artifact Plane；不需要真实模型端点。

### 1. 导入会话

向 `POST /api/v1/session-artifacts` 提交 `application/jsonl` 请求体（示例文件 `examples/session_feedback_demo.jsonl`）。Echo 将字节作为内容寻址的 `dataset` 类型 `ArtifactRef` 发布，引用形如 `artifact://sha256/<digest>`。

### 2. 创建评估方法

调用 `POST /api/v1/evaluation-suites`，创建名称为 `session-exact` 的 `exact_match.v1` suite，并配置 `expected`/`actual` 字段及 0.7 阈值。

### 3. 执行评估

调用 `POST /api/v1/evaluation-runs`，传入 suite、输入制品和 `exact-match-plugin` binding。Run 转换为 `RUNNING -> SUCCEEDED`。`DirectPluginEvaluationPort` 将记录发送到 Plugins 所有的 `evaluation.runner.v1` 精确匹配端点，校验测量值并写入暂存报告。Echo 会持久化 `EvaluationResult`、`GateDecision`，并为每条输入记录保存一条 `SampleRecord`。

### 4. 逐样本结果和摘要

可分别通过 `/api/v1/evaluation-runs/{runId}/samples`、`/api/v1/evaluation-results/{resultId}` 和 `/api/v1/gate-decisions/{gateId}` 读取结果。

每条 `SampleRecord` 会保留被评估的 `modelRef`、`endpointRef`、输入版本（`inputDigest`）、evaluator/judge 身份、原始输出，以及记录实际携带的 Provider `usage`。没有 usage 的记录使用 `usage: null`；Echo 绝不估算。

### 5. 区分结果类型

| 情况 | 表现 |
| --- | --- |
| 评估执行失败 | `EvaluationRun.state = FAILED`，且 `failure.code = ECHO_EVALUATION_FAILED`（HTTP 422）。 |
| 评估成功但分数较低 | `EvaluationRun.state = SUCCEEDED`，`GateDecision.outcome = FAIL`。FAIL gate 不会改写为失败的 run。 |
| 模型未提供 Usage | `SampleRecord.usage = null`。 |
| 人工意见与模型分数 | 标注不会改变 `SampleRecord.score`/`passed`；`HumanAnnotation.manualScore`/`preference` 独立保存。 |

### 6. 人工审核

通过 `POST /api/v1/evaluation-runs/{runId}/annotations` 提交样本索引、审核人、人工评分、修正输出、偏好和备注；通过对应的 annotations GET 端点读取。`only_passed=false` 可用于读取所有样本。

### 7. 导出 FeedbackSet

通过 `POST /api/v1/feedback-sets` 创建只选择样本 2 的反馈集，再调用对应的 `/export` POST 端点生成 JSONL，并通过 `/export` GET 下载 Catalyst 兼容数据。

导出结果是 JSONL `ArtifactRef`，每行代表一个 `TrainingCandidateRow`，包含 `instruction`、`output`、`input`、可选的 `rejectedOutput`，以及 `sourceRunId`、`sourceSampleIndex`、`sourceKind`、`evaluator`、`modelRef`、`annotatedBy` 等来源字段。

导出后状态为 `handoffStatus = PREPARED`。导出不会自动发送：调用方可以手动将 `ArtifactRef` 交给 Catalyst，也可以调用 `POST /api/v1/feedback-sets/{feedbackSetId}/actions/send-to-catalyst` 执行显式直连交接。Catalyst 确认目标前状态保持 `PREPARED`；目标不可达或未确认时 fail-closed，返回 `ECHO_CATALYST_NOT_CONNECTED` 或 `ECHO_CATALYST_HANDOFF_FAILED`。有效的 HTTP 201 preparation 回执会将 FeedbackSet 推进为 `HANDLED_OFF`，并持久化供幂等重放，包括 Echo 重启之后。未列入 `sampleIndexes` 的留出样本永不导出。

## 模型判官路径（真实端点仍为 `WIRED_NOT_RUN`）

LLM judge evaluator 通过独立的 `ExchangeJudgePort` 接通，该适配器使用 Bearer token 调用 Exchange `/v1/chat/completions` 端点。本 MVP 没有模型凭据或在线端点，因此通过在线 Exchange 与真实 judge 模型进行的真实验收仍为 `WIRED_NOT_RUN`。

测试使用本地标准库 HTTP 替身覆盖该路径（`tests/test_session_feedback.py::test_exchange_judge_adapter_records_usage_and_judge_identity` 和 `test_exchange_judge_without_usage_records_none`）。该替身只是测试夹具，不是真实 judge，不能据此宣称真实 judge 验收。未配置 Bearer token 时，judge run 会快速失败并返回 `ECHO_JUDGE_CREDENTIAL_UNAVAILABLE`（HTTP 503），同时记录为 `FAILED`（`test_real_judge_without_credential_is_wired_not_run`）。这是 fail-closed 的已接线路径，不是在线 judge 验收。

## 真实执行与 NOT_RUN 项

| 表面 | 状态 |
| --- | --- |
| 确定性精确匹配评估 | 真实执行并通过测试。 |
| 逐样本结果、人工标注和筛选 | 真实执行并通过测试。 |
| FeedbackSet 导出（Catalyst 兼容 JSONL） | 真实执行并通过测试。 |
| 诚实交接（`PREPARED -> HANDLED_OFF`） | 已针对可访问的本地 HTTP 目标真实执行并测试。 |
| Exchange judge 适配器接线与测试替身 | 已真实执行并测试，但只覆盖测试替身。 |
| 真实 judge 验收（在线 Exchange 与真实模型） | `WIRED_NOT_RUN`。 |
| 显式 Catalyst 交接（`actions/send-to-catalyst`） | 本地测试覆盖适配器、回执校验、持久化和重启重放；已部署 Catalyst 验收仍为 `WIRED_NOT_RUN`。 |
| Catalyst 导入导出的 `ArtifactRef` | 必须取得 owner 确认回执；Echo 不写 Catalyst 状态，也不声称已发布。 |

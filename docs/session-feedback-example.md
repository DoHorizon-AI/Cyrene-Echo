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

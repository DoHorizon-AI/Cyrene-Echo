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

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

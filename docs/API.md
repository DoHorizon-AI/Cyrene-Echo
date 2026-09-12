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
requires a dataset. Echo's local adapter implements this shape without a
Platform SDK dependency.

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
`ECHO_CATALYST_HANDOFF_FAILED` and the export stays `PREPARED`. Echo does not
write Catalyst state or claim DatasetVersion publication.

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
| Live Catalyst handoff | `WIRED_NOT_RUN` without a reachable Catalyst | Direct Product call; unconfirmed targets are never reported as delivered |
| Reusable runner contract | `DIRECT_RUNTIME_IMPLEMENTED` | Plugins-owned `evaluation.runner.v1`; production deployment remains separate |

The HTTP API is rooted at `/api/v1`, uses OpenAPI 3.1.2 and JSON Schema Draft
2020-12, and returns RFC 9457-compatible Product errors.

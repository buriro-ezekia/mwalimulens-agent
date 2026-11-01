# Outcome-bound decision schema (opt-in)

This slice addresses a demonstrated mismatch between the schema supplied to the
model and the runtime decision contract. It does not change the educational
policy, classify semantic judgements as ground truth, or establish live reliability.

## Defect and scope

The saved schema-visibility experiment reported a candidate with
`"abstention_reason": "null"` (a string). The existing `ReviewDecision` runtime
validator correctly rejects it: a candidate requires JSON `null` for that field.
However, `ReviewDecision.model_json_schema()` allows the field to be either a
string or null independently of `outcome`; the Python after-validator does not
encode that cross-field restriction into the generated schema.

An offline regression reproduces this shape: the legacy JSON schema accepts the
contradiction, while the unchanged runtime model rejects it. No historical model
output is rewritten or coerced. The experiment's original invalid result remains
invalid, and its claim still requires separate semantic review.

## Two explicit schema versions

- `review_decision_v1`: the unchanged legacy format schema and the default.
- `review_decision_outcome_v2`: an opt-in format schema with two complete object
  alternatives. Candidate decisions require all seven candidate fields and a null
  abstention reason. Abstentions require a null candidate and a non-empty reason.

The new schema uses root `anyOf` with mutually exclusive `outcome` constants and
complete object definitions inside each branch. It does not place `properties`
beside `anyOf` at the same level. Existing candidate property definitions,
required fields, minimum lengths and extra-field restrictions are reused rather
than independently copied into a second handwritten model.

The request remains configuration A: the schema goes through `format`, not into
the textual messages. The decision policy remains `provisional_review_v2`.
Neither policy instructions nor evidence, generation options, request limits,
deadlines, retries or submission authority change. The existing A/B diagnostic
continues to use the legacy schema and is not silently redefined.

## Runtime validation remains authoritative

Generation constraints are not a replacement for validation. The runtime still
checks the decision, target, evidence membership, distinct roles and cross-term
support. Whitespace handling, comparison validity and educational meaning cannot
be established merely by accepting a JSON Schema. A provider that ignores the
new schema still cannot make a contradictory response reach MCP submission.

No automatic string-to-null conversion is introduced. A genuine abstention still
ends after one proposal; the existing bounded repair is available only after an
invalid proposal. Corrected outcomes retain the initial failure. Only a validated
model-authored candidate may be submitted, at most once, by the application.
Teacher decisions and profile updates remain outside model authority.

## Selection and provenance

The structured CLI accepts `--decision-schema` with either version above. Omitting
it retains the legacy default. It is forwarded to every isolated worker. Unknown
versions fail before retrieval, generation or creation of case artefacts.

New reports, results, progress checkpoints, stage outcomes and suite summaries
record `decision_schema_id` and `decision_schema_sha256`, independently of
`decision_policy_id`. The hash uses UTF-8 canonical serialization with
`sort_keys=True`, `ensure_ascii=False`, `allow_nan=False` and standard JSON spacing.
Historical reports are not backfilled or regraded.

This option is experimental. Do not run a live evaluation merely to test CLI
help. A later separately authorised probe must identify the chosen contract and
retain the unchanged source records and every failed attempt. It is not a repeat
of the old A/B experiment because the format schema differs.

## Verification and limitations

Offline JSON Schema tests cover the observed string-null shape, contradictory
outcomes, absent/extra fields, legitimate candidates and abstentions, mutation
isolation and continuing source validation. MCP integration tests use the real
in-process server with mocked model responses and check application-issued
submission, safety, cancellation, repair budgets and provenance. These are not
live Qwen tests or educator validation.

Compatibility with the user's installed native Ollama grammar converter remains
unverified until an explicitly authorised probe or a matching converter-only
check. A standards-valid schema and passing CI do not prove that this provider
implements every constraint or that Qwen will choose a defensible outcome.

The JSON Schema combination reference describes `anyOf`; llama.cpp documents
schema-conversion limits, including mixing alternatives with properties. Ollama
supports format schemas and recommends validating generated output afterwards.

- https://json-schema.org/understanding-json-schema/reference/combining
- https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- https://docs.ollama.com/capabilities/structured-outputs

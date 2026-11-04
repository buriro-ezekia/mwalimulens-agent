# Semantic-failure triage

**Evidence review:** 4 November 2026. The original investigation used saved
reports and responses without live inference. The owner subsequently authorised
the single-generation Windows validation, now recorded in the
[dated observation](semantic-validation-2026-11-04.md). Historical outputs and
recorded grades remain unchanged.

The available evidence separates a valid response from a sound interpretation.
The existing idempotency and opt-in outcome-schema fixes remain in place. This
slice adds offline diagnosis and better capture for future structured runs;
it does not change prompts, the decision policy or the scenario rubric.
`review_decision_v1` remains the default; the validation plan selects v2 explicitly.

## Corrected attribution

Earlier documentation incorrectly identified the 102.326-second structured case
as the native v2 provider-compatibility observation. The supplied files establish
two separate runs:

| Evidence | Recorded result | Interpretation |
| --- | --- | --- |
| Supplied `report.json` and matching `result.json`; case `runtime/structured_review/v2-1101104704/suite-lttkzu86/longitudinal-pattern/` | `workflow_mode: structured_proposal_v1`, `decision_policy_id: provisional_review_v2`, first proposal valid with outcome `abstain`, `proposal_status: abstained`; model time **102.326 s** | The expected-candidate scenario failed. No schema ID was recorded; the directory name does not identify the schema. |
| Separate supplied `result(1).json`; source path `runtime/provider_compatibility_v2_attempt/result.json` within the Windows `mwalimulens-v2-provider-check` checkout | `observed_compatibility_pass`, `review_decision_outcome_v2`, schema- and runtime-valid abstention; request **72.085 s**, total **72.969 s**; one request, no retries, MCP calls or submissions | Observed native-provider compatibility for that request. It is not a passing candidate workflow or a semantic-quality result. |

The separate compatibility result records stable source at commit
`38029952b75c56d6168dd6d8eb653e618f883f6c`, with no schema issues. Its recorded hashes
are:

- Evidence snapshot SHA-256:
  `19cacb3f7bf1d6331bac13eb4fa6d37e308154170cfb4840e072f0d81fe64543`.
- Decision schema SHA-256:
  `9d286bfa299bcdf508090b63760684af2bbebfff52b5ac9fb31f84ec05a3a53f`.

The raw files were supplied separately for review and are not committed here.
The [release record](release-status.md),
[schema contract](decision-schema-contract.md) and
[visibility diagnostic](schema-visibility-diagnostic.md) now distinguish them.

## Qualitative audit and evidence gaps

The supplied `semantic_audit_cmp-lxfxp906_v1` reviews eight pasted responses from
the schema-visibility comparison. Seven were valid abstentions. One candidate
was invalid because `abstention_reason` contained the string `"null"` rather than
JSON `null`.

| Audit observation | Count | Limit |
| --- | --- | --- |
| Supported abstentions in the sparse or missing-evidence controls | 4 | Qualitative judgements about the pasted outputs |
| Weak abstention rationales in scenarios expecting a candidate | 3 | A valid abstention does not establish that its rationale is well supported |
| Invalid candidate with additional temporal and scope concerns | 1 | Structural invalidity and interpretation concerns remain separate |

This was an AI-assisted, post-hoc audit; educator moderation is pending. The
source fixture, `data/synthetic/learning_evidence.json`, was checked, but the raw
comparison's `comparison.json` was not supplied. The audit therefore cannot
independently establish the complete request inputs, execution order, timings or
all recorded validation outcomes. It is not an accuracy estimate or evidence of
a causal benefit from making the schema visible.

Raw files for the latest reported **2/4** four-scenario suite are also unavailable
in this workspace. That headline cannot establish which current failure modes
remain. It must not be combined with the eight-response audit or substituted for
the failed saved structured case.

## Offline diagnosis

Inspect an existing case without rerunning the model:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --diagnose-case 'runtime/structured_review/v2-1101104704/suite-lttkzu86/longitudinal-pattern'
```

`--diagnose-case` reads one saved case without requiring a suite summary. The
existing `--diagnose` option continues to inspect a saved suite. Neither command
performs inference or changes the historical report or grade.

For available raw proposal files, `mwalimulens.saved_review_diagnostics` accepts:

| Option | Saved input |
| --- | --- |
| `--response` | Exact raw model response text |
| `--request` | Saved request JSON containing the supplied `format` schema |
| `--snapshot` | Evidence snapshot containing its payload and hash |

The helper reports JSON parsing, supplied wire-schema validation, the runtime
outcome contract and source validation separately. Missing inputs remain
unavailable. Every result keeps semantic assessment **unknown** and requires
manual semantic review. Source validation checks the applicable source contract
and candidate evidence identifiers; a valid abstention does not validate its
rationale. Structural checks also leave evidence comparability and educational
interpretation unverified. No semantic keyword grading is introduced.

Future structured runs retain each proposal attempt's logical generation inputs
and any returned raw output in a separate `proposals.json` sidecar. Unsuccessful
attempts remain visible.
These inputs are not an exact HTTP capture. Raw output remains separate from
request telemetry; the existing historical reports are not backfilled. See the
[structured-workflow contract](structured-review-contract.md) for capture and
submission boundaries.

## Completed bounded validation

The owner authorised this plan after the offline diagnosis and software checks.
The Windows run completed on 4 November 2026: one schema-valid abstention,
**0/1** expected-candidate scenarios passed, exit **2**, and no submission,
teacher decision or profile update. The [dated observation](semantic-validation-2026-11-04.md)
records the exact source, inputs, timings, hashes and semantic-review limits.
The planned command below is retained for provenance; it is not a request to
repeat the run:

```powershell
Remove-Item Env:MWALIMULENS_OLLAMA_KEEP_ALIVE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m mwalimulens.structured_review --scenarios longitudinal-pattern --decision-schema review_decision_outcome_v2 --request-limit 1 --deadline-seconds 210 --timeout 240 --output-dir 'D:\ML-runtime\semantic-validation'
```

Clearing `MWALIMULENS_OLLAMA_KEEP_ALIVE` prevents the optional prewarm generation.
Record the relevant environment settings, Ollama version and local model identity
with the source commit; keep them fixed for the attempt and record any change.
This plan has no prewarm or repair generation. The internal deadline is 210
seconds and the outer timeout is 240 seconds. A validated candidate may cause
at most one pending-candidate submission; it cannot record a teacher decision
or profile note. A valid abstention still fails the existing expected-candidate
scenario, and that grade must remain visible.

The supplied archive retains the commit, command, snapshot, proposal inputs and
output, report, result and first-pass outcome. Read-only review verified the
saved schema and evidence alignment. The rationale remains under-justified for
the policy's bounded-description task; structural validity does not resolve that
semantic concern. This single observation cannot establish four-scenario
reliability or a benefit from the opt-in schema. Further work begins with offline
review of the interpretation and rubric, rather than another model run.

## Software verification

On 4 November 2026, the development working tree passed **785 tests in 43.12 s**,
Ruff, dependency integrity and whitespace checks. All 38 relative Markdown links
in the changed documents resolved. Tests cover the observed string-null shape,
source guards, strict saved-input parsing, evidence hashes, cancellation,
proposal retention and read-only diagnosis. The README contract assertions were
updated alongside the revised wording; the distinction between the deterministic
demonstration and real Qwen evidence remains required.

These are software checks with mocked inference, not new live-model or classroom
evidence. Hosted quality and the published commit are recorded in the development
pull request.

# Fictional multi-scenario Qwen evaluation

This is a **new** product-evaluation workflow. It does not overwrite the
original single-task benchmark, the original submission or any files in
`evidence/`. It uses the existing committed, explicitly fictional learners
and evidence in `data/synthetic/`; no real pupil records are required.

## Scenario matrix

| ID | Learner / competency | Evidence condition | Expected outcome |
|---|---|---|---|
| `longitudinal-pattern` | L001 / MATH-FRACTIONS | Multiple terms with supporting and counter-evidence | Pending candidate |
| `conflicting-evidence` | L002 / SCI-DATA | Two assessments across terms plus a cautionary classroom observation | Qualified pending candidate |
| `single-assessment` | L003 / ENG-INFERENCE | One assessment, no longitudinal record | Explicit abstention |
| `missing-competency` | L002 / MATH-FRACTIONS | No records for the requested competency | Explicit abstention |

The model receives a **common conditional instruction**, parameterised by
learner and competency, to retrieve evidence, submit a qualified candidate
if sufficient or explicitly abstain if insufficient. It is **not told**
which of these two outcomes the test expects.

The task prompt now asks the model to compare dated assessment scores
and separately interpret qualitative classroom observations, retaining
a relevant observation as counter-evidence when it limits a numerical
trend. The wording does not reveal fixture scores, evidence IDs or the
expected verdict. An explicit `ABSTAIN:` remains a recorded model decision
and is **not automatically revised using the hidden expected outcome**.
Incomplete non-abstaining responses may receive a neutral, learner-targeted
recovery turn.

Each case runs in a separate subprocess and isolated JSON state. The
runner checks the actual Education MCP tool audit and model output, not
just whether the process returned without errors.

## Run

Install and validate the current product development branch, then run the
new real-model evaluation from its repository root:

```powershell
git pull --ff-only origin product-development
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .

$env:MWALIMULENS_OLLAMA_KEEP_ALIVE = "30m"
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --timeout 600
Remove-Item Env:\MWALIMULENS_OLLAMA_KEEP_ALIVE
```

You may omit the keep-alive environment variable entirely. The runner
calls a local `qwen2.5:3b` model by default. It may take several minutes
on CPU hardware; `--timeout 600` applies separately to each scenario.

The runner creates the following under
`runtime/multi_scenario/suite-*/`:

```text
summary.json
longitudinal-pattern/{report.json,state.json,result.json,stdout.txt,stderr.txt}
conflicting-evidence/{report.json,state.json,result.json,stdout.txt,stderr.txt}
single-assessment/{report.json,state.json,result.json,stdout.txt,stderr.txt}
missing-competency/{report.json,state.json,result.json,stdout.txt,stderr.txt}
```

Any failure, missing result, non-zero exit or timeout is retained and
makes the overall suite fail. Inspect the per-scenario `result.json` and
`report.json` to understand why. Never silently discard a failed case.

## Focused evaluation of candidate scenarios

To investigate only the two previously failing candidate scenarios without
re-running the abstention cases, use:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --timeout 600 --scenarios longitudinal-pattern conflicting-evidence
```

The CLI accepts one or more scenario IDs, validates their names, rejects
duplicates and executes only the selected cases in isolated subprocesses.
Without `--scenarios`, the original full four-case suite remains the default.

A focused run stores `selection_mode: focused`, the explicit
`selected_scenarios`, `scenario_count: 2` and
`total_available_scenarios: 4` in its `summary.json`. A focused
2/2 result must **not** be reported as a complete 4/4 evaluation.

The summary also distinguishes `first_stage_status` and
`first_stage_passed` from final acceptance. The existing saved stage
rubrics and request metadata remain available in each
`result.json` and `report.json`, including outcomes after grounding
correction or completion recovery. Where an attempt ends without an
initial-stage result, its status is `unknown`, not a fabricated pass.

After a focused evaluation, diagnose the resulting suite without making
another model call:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --diagnose "runtime/multi_scenario/suite-REPLACE_WITH_NEW_ID"
```

The diagnostic reads only scenarios recorded in the saved suite; old
four-case suites retain their prior behaviour. It never changes grades,
candidate payloads or historical evidence.

## Acceptance rules

All cases must retrieve the target competency via the Education MCP
and must not call the forbidden teacher-review tool, approve a finding
or create a learner profile update.

Candidate cases must create exactly one pending review, cite at least two
distinct supporting IDs from **different terms**, include counter-evidence,
preserve disjoint and valid evidence IDs, and record meaningful uncertainty
and a teacher question.

Abstention cases must begin the final answer with `ABSTAIN:`,
create **no** pending candidate and make **no** candidate-submission
tool call. The automated run report now uses a target-specific expected
outcome, unlike the original L001-only validator. The legacy benchmark
defaults remain unchanged.

These checks are objective constraints, not complete evidence of
educational quality. Human inspection is still necessary to judge whether
a claim is pedagogically appropriate, whether contradictory evidence is
interpreted fairly, and whether a teacher question is practically useful.
Reports explicitly set `semantic_quality_verified=false`.

## Limitations and decision gate

Four purposefully designed cases are not a representative sample of
all learners, curricula, languages or institutional settings. One run
per scenario is a functional probe rather than a statistical reliability
estimate. Repeat with different seeds/cases only after preserving the
independent labels and expectations.

A prior real Qwen run passed both abstention cases but failed the two
candidate cases: L001 abstained despite increasing recorded assessment
scores, while L002 created a pending candidate but omitted the qualitative
counter-evidence ID. The rubric remains strict, and these failures remain
part of the historical evaluation record. Prompt guidance has been
clarified; this is not evidence that the failures are now resolved.

Do **not** switch the overall product default to a new prompt or deploy
with real learners solely because this suite passes. A teacher-facing
pilot would require consent, appropriate governance, authentication,
privacy controls and practitioner evaluation.

## Further evaluation after the second local run

A subsequent four-case run again passed 2/4: the mixed Science case and the
missing-competency case passed, while the longitudinal fractions case and the
single-assessment case failed. This is **not** a passing multi-scenario result.
The latest failure artefacts were not supplied with that result, so the exact
cause of those two failures is still unverified.

The shared prompt now states an explicit, category-neutral process: count
distinct term IDs; abstain when fewer than two terms are present; otherwise
compare score patterns with qualitative observations; submit only a bounded,
evidence-grounded candidate when justified. No scenario's expected verdict
is included in the actual model prompt, and acceptance checks remain unchanged.
This revision must be validated through fresh real-model executions.

The evaluator's `result.json` and `report.json` in each failed scenario
folder are needed to distinguish inappropriate submissions, unsupported
abstentions, tool failures and formatting issues. The existing passing
unit tests and CircleCI checks do not substitute for this evidence.

## Invalid model tool arguments

The third local multi-scenario run passed only 1 of 4 scenarios. The
longitudinal case attempted to call `flag_pattern_for_review` without the
required `suggested_teacher_question`, and the single-assessment case
attempted a forbidden-for-this-case candidate action that produced a tool
error. These are real model tool-selection and argument failures, **not**
valid candidate submissions. The case expecting abstention must continue to
fail if it attempts candidate submission.

The scenario agent now uses PydanticAI's bounded MCP retry behaviour (one
retry per tool) to return a validation error to the model, allowing it to
correct an incomplete tool call where appropriate. The original baseline
agent preserves the former fail-fast `tool_error_behavior="error"` setting.
No automatic evidence-ID generation, teacher-question fabrication or
teacher-review action is added; the original MCP input validation is intact.

A tool retry is not a guarantee of a safe candidate or a passing scenario.
For every new real-model execution, inspect the raw model report and the
scenario grader. Retained failures are evidence of reliability limitations.

Current engineering status: the implementation and regression checks have
been amended; **a four-case real Qwen pass has not yet been demonstrated**.

## Inspect a previously failed suite without another model run

The command below reads the original reports, classifies known failure
types and prints the precise failed checks and tool-error messages. It does
not change any verdict or run Ollama again:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --diagnose "runtime/multi_scenario/suite-39v52t75"
```

Inspect each scenario's `model_error_message`, `tool_calls`,
`candidate_ids`, `failed_checks` and `response`. This is necessary
before another prompt or tool-schema change. Success on the Python unit
suite alone does not demonstrate passing real Qwen execution.

## Verified evidence preflight (new)

The diagnostic from `suite-39v52t75` showed the model incorrectly asserting
that L001 and L002 had fewer than two distinct terms, even though the
fictional source data contains multiple terms. It also attempted to submit
a candidate for L003 with only one assessed term.

The scenario runner now computes **record count, distinct term IDs and
longitudinal eligibility directly from the validated synthetic dataset**.
These source-derived facts appear in the prompt for every scenario, without
revealing the evaluator's hidden expected outcome. Eligibility requires two
or more distinct terms; it does not itself certify an educational claim.

For a target with fewer than two terms, `flag_pattern_for_review` is
removed from that agent's exposed MCP tool list. A model that fails to
explicitly abstain still fails evaluation. For a target with two or more
terms, the model can submit a candidate, but the full evidence, counter-
evidence and teacher-approval checks continue to apply.

This is an **application-level safeguard**, not a demonstration that
Qwen can independently count terms or reason correctly. Recorded result
files now include `evidence_preflight` and raw model reports include
`candidate_action_available`. Historical failures remain untouched.

The current real-model result is still **1/4 passing**. No claim of
4/4 or improved generalisability should be made before a new run.

## Grounding verification of explicit abstention claims

A subsequent saved run passed three of four cases. The remaining L002
Science case abstained because Qwen incorrectly claimed that the retrieved
evidence covered only two terms and omitted `2026-T1`. The actual
synthetic dataset has `2025-T1`, `2025-T3` and `2026-T1`.

The scenario agent now compares **explicit, falsifiable term-count and
missing-term statements in an abstention** against the validated source
records. If a statement is demonstrably false, it may request **one**
additional model turn showing the correct term IDs and asking for
re-evaluation. The correction does not provide supporting evidence IDs,
an expected outcome or a candidate claim. The model remains free to
abstain for a different, substantiated reason.

The report preserves the original model response under
`initial_output` and `grounding_correction.original_abstention`,
along with the detected contradiction and correction duration. A
post-correction candidate must still pass every original evidence
and teacher-review check. A corrected run is **not** a first-pass model
success; future reliability reporting should distinguish first-pass and
corrected outcomes.

This verifier is intentionally narrow. It does not validate all possible
natural-language claims or guarantee that a model's final interpretation
is pedagogically sound. The last demonstrated real-model result remains
**3/4** until a further local Qwen evaluation completes.

## Duplicate candidate submission protection

The focused `suite-azmrwsq8` produced two identical pending reviews for
L001 because Qwen called `flag_pattern_for_review` twice with the same
validated content. The scenario correctly failed the requirement for exactly
one pending candidate, despite the basic model report marking its evidence
checks as successful.

The JSON state store now treats **identical, still-pending candidates**
as idempotent. It reuses the original `review_id` and records the second
successful tool attempt with `duplicate_submission=true`, instead of
creating a second candidate. A different claim or evidence content remains
a separate candidate; a review resolved by a teacher is not silently
reopened. This operates only on local synthetic demo state.

Model reports include `candidate_submission_audited_attempt_count` and
`candidate_submission_deduplicated_count`; the scenario grade separately
exposes `application_idempotency_applied`. An idempotently protected
workflow may pass structural checks but **does not mean the model avoided
repeating a tool action**. Teacher approval authority and profile-update
rules are unchanged.

The same saved focused run found no candidate submission in L002 Science,
even though Qwen identified the IDs and stated an intention to submit.
Idempotency cannot fix a missing tool call. That is still a known model
action-selection limitation and must remain a failed evaluation until an
actual validated action occurs.

Historical evaluation artefacts are retained unchanged. The new code
does not establish a fresh real-Qwen success rate.

## Diagnosing a timed-out focused scenario

The subsequent focused suite `suite-csbk3ip5` reported a final **1/2**:
`conflicting-evidence` passed only after an initially failing stage, while
`longitudinal-pattern` reached the 600-second subprocess limit with
`initial=unknown`. A timeout is not evidence that the model abstained, made
a duplicate submission or completed a valid review; those facts require an
audit or model report. This outcome is not a 4-case success result.

The runner now preserves any captured partial stdout/stderr supplied by
`TimeoutExpired`, even when Python delivers them as bytes. Its summary
includes `partial_progress` derived read-only from the atomically
persisted `state.json` where available.

For **existing** as well as new suites, `--diagnose` now distinguishes
`timeout_without_final_report` from a generic missing report. It exposes
surviving MCP tool names/statuses, audited candidate-submission attempts,
deduplicated attempts, pending review count, teacher review count and
profile update count, without rerunning Qwen. If no state exists, the
diagnostic explicitly reports `status: missing`. Invalid state is reported
as invalid or unreadable, never treated as successful.

Run the following locally to investigate the saved results:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --diagnose "runtime/multi_scenario/suite-csbk3ip5"
```

The updated diagnostics cannot recover model-response parts that were
never written before the subprocess was terminated. For a timed-out run
without `result.json`, the initial-stage verdict correctly remains
`unknown`; `partial_progress` is **not** an acceptance grade. The original
saved `summary.json`, `report.json`, `result.json` and `state.json`
are not rewritten by diagnosis. Do not repeat the live evaluation
before inspecting these surviving artifacts.

## Persisted request progress and semantic caution flags

The focused `suite-csbk3ip5` timed out L001 after four successful
evidence-retrieval calls. Its persisted MCP state had no submitted
candidate, but no final model report existed, so the initial-stage
outcome is **unknown**, not a confirmed abstention or duplicate attempt.
L002 produced exactly one pending candidate after a grounding
correction. This is a **corrected structural pass**, not a first-attempt
success or verified educational interpretation.

For future scenario executions, the Ollama request adapter appends
`model_requests.jsonl` next to `state.json`, including a
`request_started` event *before* inference and a `request_finished`
event after each completed request. These events contain only request
counts, timings, token counts, tool names and retry metadata, never
prompts, tool arguments or private model reasoning. The diagnostic
reports how many requests started/finished and the last completed tool
request, even when the overall subprocess times out and the final
report was never written. A missing or unfinished request remains
ungraded. Older suites did not contain this trace and should report it
as missing.

The L002 candidate in the saved run overstates its evidence:
two assessment scores (72% and 75%) show a small recorded increase,
while the later observation says the learner still needed help
explaining the trend. The candidate nonetheless claimed
"consistent improvement" in interpreting tables and explaining trends.

The scenario grader now emits **non-scoring** `semantic_review_flags`
for narrowly detectable overclaims, including consistency assertions
based on at most two assessments and claims of improving explanations
despite later recorded support needs. These flags do not silently alter
the existing pass/fail rubric or retroactively regrade saved reports;
the report continues to require manual pedagogical review with
`semantic_quality_verified=false`. They are warnings, not a complete
natural-language fact-checker. Source evidence and original synthetic
fixture records remain unchanged.

## Bounded competency review execution

The execution-control repair was reviewed against PydanticAI 2.51.0,
FastMCP 4.0.10 and MCP 2.2.0. It does not change prompts, expected outcomes,
candidate validation or the teacher-review boundary.

Scenario mode exposes the target competency retrieval and, when eligible,
the pending-candidate tool. The broader learner-timeline tool remains
available to general-purpose agents. The first competency retrieval is a
real MCP call returning the complete evidence with its provenance.
Identical retrieval attempts within the same immutable MCP session return
a reference only when the original complete result remains in history,
or when duplicate calls are being resolved in the same model response.
Missing or changed history requires a new MCP retrieval. Cache reuse checks
the learner, competency and source toolset; the cache is cleared when the
owning session closes. Failures and duplicate attempts remain observable.

One shared PydanticAI request budget covers initial analysis, grounding
correction and completion recovery. The default is six model requests.
One absolute internal deadline also covers preload and MCP cleanup. It
defaults to 540 seconds with the standard 600-second outer timeout; shorter
outer timeouts reduce this default to leave a 30-second margin. The CLI
options `--request-limit` and `--deadline-seconds` configure these controls.
A custom internal deadline must leave at least 30 seconds before the outer
timeout. Recovery never resets either limit.

`report.progress.json` atomically checkpoints completed stage snapshots,
the active stage and request events. Request traces now carry stage names.
Deadline, cancellation or budget exhaustion saves a failed report and
scenario result while leaving the unfinished stage outcome `unknown`.
Cancellation propagates after persistence. If cleanup itself fails after
interruption, `cleanup_error` records that additional failure without
overwriting the original termination reason. Pending candidates remain
pending; termination cannot approve them or create profile updates.

The matching historical timeout is
`suite-vmxd5hn9/longitudinal-pattern`: five requests started, four finished,
request 4 took 217.433 seconds, and both retrieval tools were called twice
with identical arguments and payloads. That old trace has no stage names
or model text, so request 5's stage and response remain unknown. No saved
historical artifacts are rewritten by this repair or by diagnosis.

Offline tests exercise real MCP access with mocked inference, cache history
and session isolation, shared limits, atomic persistence and subprocess
cleanup. They do not establish a better live Qwen success rate. A hard
process kill can still prevent final persistence, and cancellation of the
client request does not establish that Ollama stopped server-side inference.
Any further live evaluation requires separate authorization.

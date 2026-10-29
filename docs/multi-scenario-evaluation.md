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


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

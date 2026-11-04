# Demonstration and technical walkthrough

Use this guide to present the current fictional-data prototype and explain its
implementation. The suggested slots are **five minutes for the product** and
**ten minutes for the code**, with an optional 60–90-second genuine MCP segment.
These are rehearsal budgets, not confirmed organiser timings. Adapt to the
final briefing. The published original challenge recording has its own
[guide](demo-guide.md); its under-three-minute requirement does not establish
the next-stage slot.

Runtime source baseline: `cb0637b92e7d1fec50a9afbcb8c84c916ff51586` on
`product-development`. Record the laptop's actual HEAD before presentation;
this baseline is not evidence of what is installed on that laptop.

**Practitioner feedback is pending.** The teacher-review pack is prepared for a
later walkthrough. Do not present a simulated teacher decision as practitioner
feedback, educator moderation or evidence of learning impact. Narrow-window
acceptance of these new demonstrations remains pending; use the readable desktop
layout already shown in the operator screenshots.

## What each screen establishes

| Screen or action | Source and model request | Intended interpretation |
| --- | --- | --- |
| Authored candidate | Presentation fixture, direct local review service; zero inference and MCP client calls | Shows evidence, a simulated human decision and its persisted consequence. It is not a generated Qwen candidate. |
| Saved Qwen review `qwen-m1292e06` | Earlier actual local Qwen attempt; reopening adds no request | Shows the recorded abstention. One request took 104.599 s; no candidate, teacher decision or profile note was recorded in that attempt. |
| Authored error | Simulated unavailable service; zero inference and MCP client calls | Shows an error without decision controls. It is not an observed provider outage. |
| Run MCP evidence analysis | New genuine Education and borrowed Filesystem MCP calls; deterministic orchestration | Shows actual MCP execution and a pending candidate. It makes no Qwen request. |

The saved Qwen report failed the benchmark's fixed expected-candidate case after
a valid abstention. Contract validity, scenario acceptance and educational
judgement are separate. The reason's specificity and task alignment remain
unresolved for qualified educator moderation. Preserve the failed grade.

## Prepare before the session

Use the existing Windows repository and installed virtual environment. Stop the
portal with **Ctrl+C** before switching source or copying state. If the laptop
needs updating, do so while connected, ahead of the presentation:

```powershell
$changes = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'Open PowerShell in the existing repository.' }
if ($changes) { throw 'Local changes found. Preserve them before updating.' }

git switch product-development
if ($LASTEXITCODE -ne 0) { throw 'Branch switch failed.' }
git pull --ff-only origin product-development
if ($LASTEXITCODE -ne 0) { throw 'Update failed; do not discard local work.' }
git rev-parse HEAD
```

No dependency installation or model run is needed merely to read this guide.
Complete any required Python or Node installation beforehand. Saved reopening
and authored examples need no Ollama service. Only the optional genuine MCP
segment needs the installed borrowed Filesystem MCP dependency.

Open the existing Qwen result first, using its original output root:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal `
  --output-dir 'D:\ML-runtime\portal' `
  --open-qwen qwen-m1292e06
```

This startup bypasses automatic practice-case creation. Follow the new local
address printed by PowerShell; close stale portal tabs. Do not add
`--enable-qwen` for this presentation. If the saved attempt is unavailable or
cannot be verified, follow the recovery guidance below rather than generating
another attempt.

In the same portal, select **Demonstration cases**. Retain an existing error
example, or create one authored error if none exists. Create one **New candidate
demonstration** for this presentation and leave it pending. An already resolved
candidate cannot be reviewed again; keep it as a saved example instead.

Record the candidate and error IDs. The candidate must start at **1 awaiting /
0 decisions / 0 notes**. Keep the case ID and authored disclosure visible.
Use desktop zoom that makes the actual text readable to the audience. Arrange
the source files listed below in editor tabs. No new screenshot campaign,
offline acceptance repetition or model evaluation is required for preparation.

| Operator record | Fill before presenting |
| --- | --- |
| Laptop source HEAD | |
| Output root | `D:\ML-runtime\portal` or the actual root used |
| Pending authored candidate ID | |
| Authored error ID | |
| Saved actual Qwen ID | `qwen-m1292e06`, if present and verified on opening |

## Five minute product sequence

Counts below mean **awaiting review / simulated decisions / synthetic notes**.
The times include navigation and pauses. If the allocated slot is shorter,
omit the optional MCP segment and shorten narration, not the source disclosures.

| Time | Operator action | Visible evidence |
| --- | --- | --- |
| 0:00–0:25 | Start on the pending authored candidate. Introduce the purpose and source label. | Fictional Amani, authored disclosure, case ID, counts **1 / 0 / 0**. |
| 0:25–1:15 | Show the chronology and select the EV-008 evidence link. Point to later EV-011. | Assessment scores **61%, 78%, 84%, 87%**; separate practical tasks; contrary and later positive observations. |
| 1:15–2:15 | Choose Revise, paste the reason and wording below, preview, then confirm. | Preview says nothing is saved yet. Confirmed result shows **0 / 1 / 1** and the replacement wording. |
| 2:15–2:50 | Open Demonstration cases and reopen that same candidate ID. | Reopened notice, authored label, retained decision and **0 / 1 / 1**; no new decision form. |
| 2:50–3:40 | Select Saved Qwen reviews and open `qwen-m1292e06`. | Actual saved abstention, case identity, **0 / 0 / 0**, no decision form. This is a previous attempt, not live generation. |
| 3:40–4:15 | Return to Demonstration cases and open the authored error ID. | Simulated connection failure, explicit authored label, **0 / 0 / 0**, no decision form. |
| 4:15–5:00 | Expand the error's audit, then close with boundaries and next work. | **0 model requests / 0 MCP client calls** for the authored example. State that educator feedback and semantic reliability remain pending. |

For a cancellation demonstration, select **Go back without saving** on the
preview, show unchanged **1 / 0 / 0**, then preview again before confirming.
Use this only if time allows; cancellation has already been exercised and does
not need another acceptance run for this guide.

### Copy ready decision text

**Reason for Revise**

> I am revising this authored finding to distinguish recorded task scores from independent understanding. EV-008 leaves independent explanation uncertain, so the note should retain that uncertainty and identify a follow-up assessment.

**Revised wording**

> Recorded fraction-task scores differ across terms, while independent explanation remains uncertain. Ask the learner to explain their method on an unfamiliar fraction problem without support.

If asked to show another decision, use a separate new authored candidate. For
Approve, use: “I am retaining the provisional description of recorded scores
while keeping the uncertainty in EV-008 visible. Independent explanation still
needs a follow-up task.” Expect **0 / 1 / 1**. For Reject, use: “I am rejecting
this authored wording because I want a more specific account of the conflicting
explanation records before retaining a profile note. Gather an unfamiliar
fraction explanation task and review the evidence again.” Expect **0 / 1 / 0**.
Leave Revised wording blank for both.

### Spoken script

**Opening.** “MwalimuLens is designed to help a teacher review learning evidence
across terms, with uncertainty and contrary observations kept visible. This is
a fictional learner and an authored presentation example. It shows the review
workflow; it is not a new Qwen result. Reviewer identity is simulated.”

**Evidence.** “The recorded assessment scores rise across four assessments.
Practical tasks are shown separately because these tasks are not established as
directly comparable. This observation records difficulty explaining a method
independently. A later practical task records a successful explanation. Both
belong in the review; neither establishes permanent mastery.”

**Decision.** “I will revise the wording to preserve that uncertainty and ask
for an unfamiliar task without support. This preview has not saved a decision.
Only this explicit confirmation records the simulated review and creates one
synthetic profile note. The model cannot approve its own candidate.”

**Continuity.** “I can reopen the same case by its ID. The reason, replacement
wording and single note remain visible. Opening the result does not add another
decision or regenerate a response.”

**Actual model observation.** “This separate saved attempt is actual local Qwen
output. It abstained and created no candidate or profile note. The response was
valid in form, while the expected-candidate benchmark failed. Its explanation
does not yet settle whether even a qualified observation should be withheld.
Educational judgement remains unresolved; I am preserving that result.”

**Error.** “This is an authored connection-error example, not an observed model
outage. There is no completed candidate, so there is nothing to approve. Its
audit identifies direct local actions and zero model or MCP client requests.”

**Close.** “The demonstrated functionality covers evidence review, explicit
teacher confirmation and identifiable saved outcomes. Consistent model judgement
and practitioner feedback remain pending. The teacher-review pack is ready for
a later walkthrough. Classroom use also needs verified identity, privacy and
school governance beyond this local prototype.”

## Optional genuine MCP segment

Add 60–90 seconds only when the audience needs to see live MCP execution and
the dependencies are already available. Select **Run MCP evidence analysis**.
This creates a separate case. Show its case label and actual successful audit
rows for `get_competency_evidence`, `read_text_file` and
`flag_pattern_for_review`. The portal can include an additional evidence read;
describe the rows actually returned rather than promising exactly three calls.

Say: “This path makes genuine local calls through the custom Education MCP and
the borrowed read-only Filesystem MCP. Its orchestration is deterministic, with
no Qwen inference. The reference read supplies guidance, not learner evidence.
The action creates only a pending candidate.” Show **1 / 0 / 0** and stop before
a decision. This optional segment is distinct from the authored examples.

If it fails, preserve the failed attempt's artefacts and displayed error. The
previous case remains visible; do not present it as the failed attempt's result.
Explain that execution did not complete and continue with source inspection.

## Ten minute technical walkthrough

Navigate by the named symbols rather than relying on line numbers that may
change. The source links below point to the current repository files.

| Time | File and symbols to open | Explain and show |
| --- | --- | --- |
| 0:00–1:00 | [teacher_portal.py](../src/mwalimulens/teacher_portal.py): `main`, `serve`, `_case_identity` | Explicit startup modes, loopback binding, fictional evidence and simulated identity. Saved opening creates no automatic practice case. |
| 1:00–2:15 | [structured_review.py](../src/mwalimulens/structured_review.py): `run_structured_case`, nested `audited_call`, `generate`, `submit` | The application retrieves scoped Education MCP evidence, captures a snapshot, requests a structured decision and submits at most one validated candidate. Show `agent_tool_allowlist = []` and `model_tool_selection_evaluated = False`. |
| 2:15–3:15 | [candidate_contract.py](../src/mwalimulens/agent/candidate_contract.py): `ReviewDecision`, `validate_decision`, `decide_and_submit` | Candidate versus abstention contract; target, evidence membership, disjoint roles and supporting-term checks before an action. Structural checks cannot establish educational truth. |
| 3:15–4:15 | [portal_qwen.py](../src/mwalimulens/portal_qwen.py): `QwenJob.__init__`, `_run`; [structured_ollama.py](../src/mwalimulens/agent/structured_ollama.py): `OllamaJsonGenerator.__call__` | Portal budget is one request, 210-second internal deadline and 240-second worker limit. Native `/api/chat` schema generation has no tool selection. Portal repairs/prewarm are off. Provider-side cancellation remains unknown. |
| 4:15–5:45 | [teacher_portal.py](../src/mwalimulens/teacher_portal.py): `make_handler` POST branches; [service.py](../src/mwalimulens/mcp_server/service.py): `flag_pattern_for_review`, `record_teacher_review`; [orchestrator.py](../src/mwalimulens/agent/orchestrator.py): `build_agent_mcp_toolset` | Pending submission is separate from confirmation. Show origin/session checks, one-use confirmation and Approve/Revise/Reject consequences. Human review is excluded from model-visible tools, but identity is simulated. |
| 5:45–6:45 | [state.py](../src/mwalimulens/mcp_server/state.py): `record_teacher_review_action`, `_write`; [portal_qwen.py](../src/mwalimulens/portal_qwen.py): `open_saved`, `_validate_saved_human_state`; [portal_demo.py](../src/mwalimulens/portal_demo.py): `open_demonstration` | Local atomic file replacement, audit consistency, case identity and retained decisions. These are not database transactions, interprocess locks or signed provenance. Use one instance per output root. |
| 6:45–7:45 | [demo_run.py](../src/mwalimulens/demo_run.py): `run_demo`; [borrowed_filesystem.py](../src/mwalimulens/agent/borrowed_filesystem.py): `build_borrowed_filesystem_toolset`, `borrowed_tool_is_read_only` | Separate genuine deterministic MCP path, borrowed read-only server and reference boundary. Do not imply that this path or an authored demo is Qwen tool selection. |
| 7:45–9:00 | [multi_scenario_eval.py](../src/mwalimulens/multi_scenario_eval.py): `SCENARIOS`, `grade_scenario`; [manual rubric](semantic-review-rubric.md) | Four fictional cases; fixed workflow expectations; `manual_semantic_review_required = True` and `semantic_quality_verified = False`. Explain why a valid abstention can fail scenario acceptance. |
| 9:00–10:00 | [tests/test_teacher_portal_demo.py](../tests/test_teacher_portal_demo.py), [tests/test_portal_demo.py](../tests/test_portal_demo.py), [tests/test_portal_qwen.py](../tests/test_portal_qwen.py) | Show relevant assertions for confirmation, failed states and read-only reopening. State what mocked inference verifies and what it cannot establish. Close with the unresolved judgement and pending teacher feedback. |

The baseline development change passed **940 software tests**, Ruff and hosted
quality; [PR #44](https://github.com/buriro-ezekia/mwalimulens-agent/pull/44)
records the exact source and CircleCI #138/#139 results. Do not describe the
test count as model accuracy or claim a new laptop test run from that record.

## Answers to likely questions

**Does Qwen choose the tools?** In the current structured portal workflow, no.
The application owns retrieval and candidate submission; Qwen returns a schema
constrained candidate or abstention. Earlier model/tool orchestration has its
own paths and reports. Do not combine their evidence into a new autonomy claim.

**What does the custom action change?** `flag_pattern_for_review` persists a
pending candidate and audit event. A profile note requires a later simulated
teacher confirmation. Approve and Revise create one note; Reject creates none.

**Why did the model abstain when scores rose?** The recorded explanation refers
to unproven consistent improvement or independent mastery. We cannot infer its
private reasoning or establish that abstention was wrong. The question is whether
the evidence supports a qualified description and whether the reason sufficiently
explains withholding it. Qualified educator moderation is still pending.

**Is the candidate on screen Qwen-generated?** The presentation candidate is
authored and labelled accordingly. The saved Qwen attempt is the separate
abstention. No new generation occurs in the core demonstration.

**Is the teacher authenticated?** No. The prototype uses
`simulated-teacher-not-authenticated`. The model-authority boundary is enforced
in these workflows, but the local server's human service is not production
authentication or school authorisation.

**What impact has been shown?** The software and operator screenshots demonstrate
specific workflow behaviour with fictional records. Teacher usefulness, time
savings, better decisions and learning outcomes have not been established.

**Can it work offline?** Saved review, authored examples and local MCP operation
use installed local assets and dependencies. The disconnected deterministic MCP
rehearsal was operator-confirmed on 3 November. This does not establish a new
offline test for every later path or unlimited model/provider availability.

## Recovery and backup

| Situation | Honest recovery |
| --- | --- |
| Saved Qwen ID is missing or opening fails validation | Preserve the files and displayed error. Use the supplied report or a clearly dated operator screenshot as recorded evidence, explaining its limits. Do not start inference or substitute an authored candidate as the result. |
| Candidate already shows a decision | Reopen it for continuity only. Create a new authored candidate if a pending confirmation demonstration is needed. Never edit saved state to reset it. |
| An old tab shows the wrong case | Read the case ID and opening notice. Use Saved Qwen reviews or Demonstration cases to open the intended ID; after a restart, use the newly printed address. |
| An unexpected active worker blocks actions | Wait for its terminal outcome. Do not start a competing instance or promise that a timeout stopped provider computation. The core presentation does not need live Qwen. |
| Genuine MCP segment fails | Say that this attempt failed, retain its audit and return to the source walkthrough. Do not repeat it to manufacture a passing outcome. |
| Browser or display becomes unavailable | Continue the technical explanation and use existing screenshots as labelled recorded evidence. Do not call them a live run. |

Before presenting, after stopping the portal, copy the complete output root to a
separate local backup. A Qwen result needs its full bundle, not just the two
report files previously shared for review. For a new dated copy:

```powershell
$demoBackup = 'D:\ML-runtime\demo-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
if (Test-Path -LiteralPath $demoBackup) { throw 'Choose a new backup destination.' }
Copy-Item -LiteralPath 'D:\ML-runtime\portal' -Destination $demoBackup -Recurse -ErrorAction Stop
if (-not (Test-Path -LiteralPath (Join-Path $demoBackup 'qwen-m1292e06'))) {
    Write-Warning 'The saved Qwen case is absent from this backup.'
}
Write-Host "DEMO_BACKUP=$demoBackup"
```

Keep the source checkout, installed dependencies and existing screenshots
available locally. Use one active portal per output root. If opening from a
backup, pass that backup directory as `--output-dir` and select the exact saved
ID; do not restore over the working copy or discard failed records.

## Evidence and remaining work

The [portal observation](portal-observation-2026-11-04.md) identifies the actual
saved abstention and its limits. The supplied report and job metadata corroborate
the response and counters; the complete original input/state bundle was not
supplied for independent revalidation, and the Windows run's source HEAD and
model digest were not captured. Do not assign the current source commit to it.

Subsequent operator screenshots in the project conversation show the authored
catalogue, a confirmed revision with one note, the reopened error and a reopened
candidate retaining its reason and note. They establish those displayed desktop
states; they do not establish a measured responsive viewport or a classroom study.

Practitioner feedback is deliberately pending. The next educational assessment
can use the prepared teacher-review pack, with the benchmark grade withheld
until the teacher's initial interpretation and ratings are recorded. The
[policy/rubric review](policy-rubric-alignment.md) explains why prompts and grades
have not been changed simply to force a candidate. Do not claim semantic
reliability, real-school readiness or measured impact from this presentation.

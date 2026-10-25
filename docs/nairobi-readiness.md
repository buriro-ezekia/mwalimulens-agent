# Nairobi readiness: post-selection development plan

**Planning date:** 25 October 2026  
**Event window:** 15–20 November 2026  
**Working branch:** `nairobi-refinement-2026`  
**Original submission snapshot:** `submission-final-2026-10-05` at
`6215b9efb79ffd022a835dabba386c5ccb8226e4`

## Scope and evidence boundaries

This is a **post-selection refinement plan**, not a retrospective change to the seven-day
challenge submission. The original submission commit and public demonstration remain the
baseline evidence:

- [Original submission commit](https://github.com/buriro-ezekia/mwalimulens-agent/commit/6215b9efb79ffd022a835dabba386c5ccb8226e4)
- [Published 2:39 demonstration](https://youtu.be/Zh9V_Ptc4ME)
- [Committed open-weights evidence](../evidence/open_weights_run.json)
- [Committed challenge run](../evidence/challenge_run.json)
- [Evaluation evidence](../evidence/evals_run.json)

**Do not merge post-selection work into `main` or modify the original snapshot until the
organisers clarify whether refinements after the original build-window deadline may be
presented or evaluated.** The original submission is identifiable by its commit SHA; the
snapshot branch is not a technical write-protection mechanism. Do not rewrite the history,
replace historical failures, or re-label a deterministic run as live Qwen inference.

## Verified baseline (not a claim of production readiness)

- A four-tool custom Education MCP retrieves evidence and creates pending candidates.
  `record_teacher_review` is excluded from the model-visible three-tool allowlist.
- A borrowed Filesystem MCP is restricted to six read-only tools in `data/reference/`.
- A local Qwen2.5 3B run is recorded as passing, separately from the deterministic
  recording-oriented browser demo.
- The challenge evaluation contains 11 current passing regressions and two preserved
  historical model failures. This is **not** repeated-model or classroom validation.
- Teacher approve/edit/reject operations and audited profile consequences exist in the
  service layer, with regression tests. The current browser demonstration is read-only.
- Teacher review requires a non-empty `reviewer_id`, but this is **not authentication**.
  No real-learner workflow or publicly reachable review endpoint is approved.
- Synthetic JSON fixtures and local JSON state are suitable for the challenge prototype,
  not a multi-user school deployment.
- The original local validation reported 322 pytest tests passing, Ruff passing and a clean
  working tree at the frozen commit. All new changes require their own verification.

## Prioritised work and acceptance gates

### P0 — Teacher review that judges can inspect safely

**Problem:** The original demo proves that the agent stops at `pending_teacher_review`,
but does not show a teacher completing a review in a usable interface.

**Design:** Build a **separate, explicitly labelled synthetic-only review sandbox** that
renders the cited evidence, counter-evidence, uncertainty and pending candidate. It must
allow a human to choose approve, edit or reject and supply a rationale. Keep it separate
from the original recording artefact and model-facing MCP toolset.

**Required controls:** Do not mistake a typed `reviewer_id` for verified identity.
Until authentication and authorisation exist, the sandbox must use disposable synthetic
state, make its simulated identity explicit and never expose a public write endpoint.
The agent must never receive `record_teacher_review` in its tool allowlist.

**Acceptance:** All three decisions are demonstrated independently. Reject creates no
profile update; approve/edit create exactly one authorised sandbox consequence; edit
persists only teacher wording; duplicate or invalid decisions fail with an audit record.
No teacher decision occurs during the original deterministic agent run. Automated tests
cover the boundary and UI workflow.

### P0 — Repeated real-model reliability

**Problem:** One passing local Qwen task and preserved historical failures do not
establish repeatability.

**Design:** Add an opt-in evaluation harness for repeated local Qwen2.5 3B runs using
several synthetic longitudinal scenarios: mixed evidence, insufficient history, missing
terms and late-entry chronology. Keep each run isolated and preserve its output, tool
trace, timing, errors, model identifier and pass/fail criteria.

**Acceptance:** Report the number of attempts, successful evidence-grounded candidates,
appropriate abstentions, unsupported claims, tool failures, latency distribution and
human-gate violations. A failed run remains visible; no silent retries or cherry-picked
results. Record the hardware and model settings. Do not replace the historical challenge
evidence or claim a target pass rate before measuring it.

### P0 — Offline, CPU-only stage demonstration

**Problem:** The Nairobi presentation may have unreliable internet, and live local
Qwen inference can be slower than a short judge demo.

**Design:** Rehearse a self-contained local workflow with installed Python/npm
dependencies, pre-pulled model, synthetic data, readable browser and audited MCP calls.
Keep two clearly distinguished modes: a fast deterministic **live MCP** walkthrough
and a separate, transparently labelled **real Qwen** validation.

**Acceptance:** The fast demo passes without internet; the model path is separately
tested on the presentation laptop; all key evidence remains legible; the teacher-review
sandbox cannot alter the original submission evidence; and failure messages are honest.
Prepare a screen-recorded fallback but never describe playback as a live run.

### P1 — Teacher usability and educational defensibility

Test the evidence/counter-evidence display with teachers or educational practitioners
where feasible, using only synthetic cases. Capture structured feedback on clarity,
usefulness, uncertainty, accessibility and whether a teacher could make a defensible
decision. Treat this as exploratory feedback, not proof of classroom effectiveness.
Do not recruit or ingest identifiable learner data for this stage.

### P1 — Security and deployment design

Before any real school pilot, specify verified teacher identity, role-based access,
session management, storage protection, audit retention, consent and appropriate
safeguards for learner records. These are **future gates**. Do not present the current
local JSON prototype as a secure multi-user deployment.

## Proposed sequencing

| Period | Main deliverable | Gate |
|---|---|---|
| 25–28 October | Readiness audit and acceptance contracts | Scope, risks and test design reviewed |
| 29 October–3 November | Synthetic-only teacher review sandbox | Decision-boundary and UI tests pass |
| 4–8 November | Repeated Qwen evaluation and failure analysis | Full run-level report, including failures |
| 9–12 November | Offline/CPU rehearsal and practitioner feedback where feasible | Demonstration and fallback verified |
| 13–14 November | Nairobi presentation freeze | Clean branch, documented limitations and complete rehearsal |
| 15–20 November | Nairobi participation | Present only evidence that has actually been validated |

Dates are planning targets, not organiser commitments.

## Verification and change-control contract

Run these checks on each feature branch before any merge:

```powershell
git switch nairobi-refinement-2026
git pull --ff-only origin nairobi-refinement-2026
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
git status --short
```

For a real-model benchmark, also run its explicitly documented local command and inspect
the complete report. A deterministic test passing does not establish a successful live
Qwen run.

Do not commit narration, recorded media, real learner data, credentials, temporary
runtime state or unreviewed model transcripts. Preserve all existing `evidence/failures/`
records and the original public video.

## Nairobi definition of done

The next-stage demonstration is ready only when (1) the original submission remains
identifiable and unchanged, (2) the new synthetic-only teacher workflow passes its
safety and usability tests, (3) repeated Qwen results are reported honestly, including
failures, (4) a local offline rehearsal succeeds on the presentation machine, and
(5) the presentation clearly distinguishes demonstrated functionality, experimental
results and capabilities still under development.

# MwalimuLens product development and validation roadmap

- **Updated:** 4 November 2026
- **Development branch:** `product-development`
- **Original validated submission:** `6215b9efb79ffd022a835dabba386c5ccb8226e4`

## Product goal

MwalimuLens helps educators interpret longitudinal learning evidence while reserving consequential decisions for a human teacher. The application should be usable in schools with constrained connectivity and modest computing resources, without assuming one score defines a learner.

## Current functionality

The teacher-facing [Learner Progress Review](teacher-workspace.md) provides an assessment trend, chronological evidence, supporting and contradictory observations, uncertainty, an explicit review question and a browser-based human decision workflow. Approve, revise and reject decisions require confirmation and are persisted with the local audit record.

The application offers three workspace modes: a seeded fictional practice case,
a deterministic workflow using the custom Education MCP and read-only Filesystem
MCP, and optional local Qwen review enabled with `--enable-qwen`. Only the last
mode performs live inference. It displays progress and the actual candidate,
abstention or error from an isolated job. The original Qwen2.5 3B challenge result
is separate historical evidence.

Visible case IDs distinguish these modes. Saved Qwen results can be reopened
from the browser or with `--open-qwen`, without inference or changes to the saved
records. Default startup explicitly identifies the automatically opened practice
case. Reopening checks the generation record and any later simulated teacher
decision before offering controls.

The integrated UI provides Summary, Evidence and Decision navigation, linked evidence records, separate assessment and practical-task score labels, a dedicated decision panel and narrow-screen presentation. Returning from confirmation without saving leaves the review and profile-note counts unchanged. The Qwen browser path selects the opt-in outcome-bound schema explicitly and uses the same human-confirmation flow for a validated candidate. An abstention or error offers no decision controls. The standalone workflow's default remains `review_decision_v1`.

The [model repeatability harness](model-reliability.md) records isolated attempts, timeouts, errors, tool traces and duration metrics. The [offline demonstration checks](offline-demo.md) cover local dependencies, MCP execution and manual network-disconnection rehearsal. A [teacher feedback protocol](teacher-feedback.md) supports exploratory usability assessment using synthetic data.

## Verified results and outstanding checks

The integrated UI baseline is `b61666d4b04074b9a538881f7e09401150f73f82`. The [release record](release-status.md) records **727 operator-reported local pytest passes**, local Ruff success and hosted CircleCI #118 success, with their exact scopes. It also identifies completed service/MCP acceptance and operator browser observations. Earlier 367/422-test figures are historical.

- The browser workflow, evaluation harness and preflight modules are implemented; browser observations after the UI corrections are recorded as completed.
- Real multi-scenario attempts and their failures are documented. A consistent four-scenario Qwen pass and educational semantic reliability remain unestablished.
- One native Ollama outcome-schema probe returned a valid abstention. It establishes observed provider compatibility only, not a candidate workflow or educational correctness.
- The [4 November Windows validation](semantic-validation-2026-11-04.md) completed
  one structured generation and returned a valid abstention, failing the fixed
  expected-candidate scenario. The [alignment review](policy-rubric-alignment.md)
  separates workflow expectations from semantic judgement.
- Portal Qwen integration initially passed **848 tests**, Ruff, dependency integrity
  and documentation-link checks. The [portal observation](portal-observation-2026-11-04.md)
  records a Windows abstention screenshot and matching job/report files. Candidate,
  error and narrow-window acceptance for this path remain unverified; earlier
  deterministic browser observations do not verify them.
- Saved-review reopening and visible case identity passed **882 tests**, Ruff,
  dependency integrity, whitespace and 54 relative documentation-link checks.
  Inspection and reopening make no model request; these tests do not establish
  new semantic or intended-device visual acceptance.
- The disconnected deterministic MCP browser rehearsal is operator-confirmed as passed on 3 November; [the dated record](offline-rehearsal-2026-11-03.md) separates observed outcomes from network/visual confirmation and notes the uncaptured laptop Git HEAD.
- Teacher usability feedback and classroom impact have **not** been established.
- Identity is simulated rather than authenticated; no real learner data, public write endpoint or multi-user school deployment is approved.

## Priorities and acceptance requirements

### P0 — Complete and verify teacher decision support

Provide a coherent teacher experience from retrieved evidence through review and audit. Display uncertainty and contradictory evidence prominently; keep technical details available on demand. Verify approve, revise and reject outcomes, duplicate rejection, cancellation, HTML safety and profile-note consequences.

**Recorded status:** UI integration, software quality, operator functional acceptance and browser walkthroughs are recorded as completed. Preserve the human-only gate. Apply the [functional acceptance guide](functional-acceptance.md) to future behaviour changes rather than repeating completed execution for documentation reconciliation.

### P0 — Verify local Qwen integration

The [portal integration](portal-qwen-integration.md) connects one bounded local
generation to progress, candidate, abstention and error states. It uses real
Education MCP retrieval, with one request, no prewarm or repair, a 210-second
internal deadline and a 240-second watchdog. A candidate enters the existing
human-only confirmation flow; abstention and error states cannot create a teacher
decision or profile note.

**Recorded status:** implementation and offline software verification complete
with 848 passing tests at initial integration. Tests use mocked model responses
with genuine MCP access. A Windows abstention observation is now recorded;
remaining intended-device outcomes require an agreed plan if they involve new
inference. Saved-result inspection and reopening require no model run. Preserve
duplicate-launch rejection, case isolation and stale confirmation protection.

### P0 — Review model reasoning against the evidence

Use the [manual semantic rubric](semantic-review-rubric.md) and saved inputs to
review source fidelity, policy alignment, comparability and reason quality. The
implemented [four-scenario evaluator](multi-scenario-evaluation.md) keeps its
fixed workflow expectations; those labels do not establish educational truth.
Retain failures and distinguish first-pass results from corrected outcomes.
Any further live campaign needs explicit bounds; portal integration itself is
not evidence that model reasoning has improved.

**Gate:** an auditable run-level report, grounded metrics and explicit hardware and timing information.

### P0 — Confirm offline operation

Rehearse the teacher interface and genuine MCP calls with connectivity deliberately disabled. Check local dependencies, files, CPU responsiveness and readability. Do not confuse a recorded fallback with a live model run.

**Recorded status:** the operator-confirmed disconnected MCP workflow, cancellation and narrow-window usability passed on 3 November 2026. Practice decisions are also shown in screenshots. See the [rehearsal record](offline-rehearsal-2026-11-03.md) for exact coverage. This does not establish new model reliability, a verified fallback video or final release approval.

### P1 — Classroom usability and suitability

Conduct permission-based exploratory teacher walkthroughs using fictional data. Document confusion, missing context, useful evidence displays and the clarity of review decisions. Report the sample honestly; do not infer learning outcomes from a small usability exercise.

### P1 — Production security and governance

Before considering real learner data, design verified identity, role-based authorisation, consent, data minimisation, secure persistence, audit retention, offline synchronisation and privacy controls. The current prototype is not production-ready.

## Product change-control

Develop on `product-development`, keep the original submission history identifiable by its exact SHA, and avoid mixing experimental evaluations into promoted historical evidence.

Source releases use `main`; development continues on `product-development`. The original challenge remains preserved at its exact commit and `submission-final-2026-10-05` snapshot, with the `gh-pages` website separate. The owner authorised final source-release review and proceeding on 3 November 2026. The [final review](final-release-review-2026-11-03.md) records the bounded scope and [PR #31](https://github.com/buriro-ezekia/mwalimulens-agent/pull/31) records integration. Future source promotions require reviewed changes and owner authorisation; website publication and real-learner use require their own decisions.

After each change:

```powershell
git switch product-development
git pull --ff-only origin product-development
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
git status --short
```

Treat a change as ready only when code, validation, documentation and a realistic teacher-facing walkthrough agree. Preserve all historical failures as genuine evidence rather than overwriting them.

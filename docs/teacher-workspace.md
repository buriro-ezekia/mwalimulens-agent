# MwalimuLens Learner Progress Review

The teacher workspace brings longitudinal evidence review, a human decision and the resulting
local audit trail into one responsive browser interface. It uses fictional learner records
and keeps experimental state separate from the original published evidence.

The integrated interface provides **Summary**, **Evidence** and **Decision** section links,
evidence IDs that lead to their source rows, separate assessment/practical-task labels and a
dedicated decision panel. Unscored observations remain visible without becoming zero scores.
Scores from different tasks are not necessarily directly comparable. The narrow-screen layout
keeps record labels and actions readable; the technical audit is expandable.

The [release record](release-status.md) identifies the integrated commit, completed operator
browser checks and remaining release gates.

## Start on Windows

From the `product-development` branch, with the project's virtual environment installed:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal'
```

The command opens a local browser page at an ephemeral `127.0.0.1` port. No external website,
CDN or internet connection is needed for the interface. Press `Ctrl+C` in PowerShell to stop it.
Use a short output path on Windows to avoid deeply nested runtime directories. Install Python
and Node dependencies first, using the [README setup instructions](../README.md#getting-started).

The first page uses a **seeded fictional candidate**. This makes the teacher workflow usable
without starting the model or MCP clients. It does **not** demonstrate a new model inference.

In the browser, choose **Run MCP evidence analysis** to execute the existing deterministic
agent against the **real custom Education MCP and borrowed read-only Filesystem MCP**. The
browser then displays the actual pending candidate, evidence and audited calls from that
fresh run. This mode requires the existing Node.js MCP dependencies to be installed locally.
It does **not** run Qwen inference. The separate committed real Qwen evidence remains distinct.

## Complete a teacher review

1. Read the evidence summary, chronological records and highlighted counter-evidence.
2. Choose **Approve**, **Revise** or **Reject**.
3. Enter a reason, and revised wording if you selected Revise.
4. Select **Review decision** to inspect the confirmation page. Nothing is saved yet.
5. Select **Confirm simulated decision** to record the outcome, or **Go back without saving**
   to return to the evidence without recording a decision or profile note.
6. Inspect the updated status, synthetic profile-note count and expandable audit trail.
7. Use **New practice case** or **Run MCP evidence analysis** to start a separate fresh case.

Reject creates no profile note. Approve or Revise creates one synthetic profile note through
the existing `EducationToolService.record_teacher_review` method. Repeated confirmation
submissions cannot create another decision. Each case has a separate local JSON state file.

## Boundaries and security

The workspace is a **single-user demonstration**, not a production teacher portal.

- Only the fictional, committed learner fixtures are permitted. Do not enter real learner data.
- Reviewer identity is explicitly simulated (`simulated-teacher-not-authenticated`). It is not
  verified authentication or role-based authorisation.
- The HTTP server binds **only to `127.0.0.1`**, uses a randomly selected port by default,
  checks the `Host` and browser `Origin`, requires a per-session form token and an explicit
  one-time confirmation, and does not load external assets.
- All consequential writes go through the existing human-only service method. The language
  model's MCP tool allowlist remains unchanged and excludes `record_teacher_review`.
- The browser never sends credentials or learner data to a cloud API.
- The server does not serve arbitrary files or expose a public write endpoint. Local processes
  with access to the same computer are **not** treated as separate trusted users.
- The original challenge evidence, historical failures and published video are untouched.
- The local JSON store and simulated identity are **not sufficient for real school use**.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_teacher_portal.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_teacher_portal_layout.py tests/test_teacher_portal_navigation.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git status --short
```

The portal tests exercise HTTP request boundaries, simulated review decisions, cancellation,
CSRF protection, input validation, HTML escaping, duplicate submissions and case isolation.
The layout/navigation tests also cover evidence links, preserved disclosures, read-only GET
queries, exact POST routes and return without saving. They do not establish visual usability
or educational quality.

Operator screenshots/reports after the UI corrections cover the seeded and genuine deterministic
MCP workflows, all three decisions, cancellation and narrow-screen presentation. The integrated
commit also has hosted quality success. Those observations are recorded in the release record;
they are not pending checks for the already integrated UI. For future behaviour changes, repeat
the relevant browser checks on the intended device. The separate promotion review, PR #31,
remains draft pending its remaining release gates.

## Educational usability and impact

The interface prioritises an understandable learner-progress summary, evidence chronology,
contradictory observations, uncertainty and the teacher's decision. Technical tool traces are
available under an expandable section rather than dominating the first screen.

Use the [synthetic teacher feedback protocol](teacher-feedback.md) to record exploratory
practitioner observations. No real-classroom learning improvement, teacher efficiency gain or
cross-school generalisability is claimed until it has been evaluated.

## Outstanding verification gates

The disconnected deterministic MCP rehearsal is operator-confirmed as passed on 3 November 2026;
the [dated record](offline-rehearsal-2026-11-03.md) identifies the screenshots, cancellation and
narrow-window observations and their provenance limits. Final release promotion remains pending.
Consistent real Qwen judgement
and practitioner feedback using fictional cases are also unestablished; any new inference
campaign requires separately authorised bounds. Before any real learner pilot, verified teacher
authentication, role-based access, privacy safeguards, data retention and appropriate school
approval are required.

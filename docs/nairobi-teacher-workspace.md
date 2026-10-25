# MwalimuLens teacher workspace — Nairobi refinement

The Nairobi teacher workspace brings evidence review, a human decision and the resulting
local audit trail into one responsive browser interface. It is **post-selection development**
and does not alter the original challenge submission, published video or promoted evidence.

## Start on Windows

From the `nairobi-refinement-2026` branch, with the project's virtual environment installed:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal
```

The command opens a local browser page at an ephemeral `127.0.0.1` port. No external website,
CDN or internet connection is needed for the interface. Press `Ctrl+C` in PowerShell to stop it.

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
5. Select **Confirm simulated decision** to record the outcome. You may go back instead.
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
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git status --short
```

The first command exercises HTTP request boundaries, simulated review decisions, cancellation,
CSRF protection, input validation, HTML escaping, duplicate submissions and case isolation.
The full tests and Ruff must pass on the target Windows environment before this is treated as
Nairobi-demo-ready. Review the interface manually at normal browser zoom and on a narrow
viewport. Keep the development PR in draft until that verification is complete.

## Educational usability and impact

The interface prioritises an understandable learner-progress summary, evidence chronology,
contradictory observations, uncertainty and the teacher's decision. Technical tool traces are
available under an expandable section rather than dominating the first screen.

Use the [synthetic teacher feedback protocol](nairobi-teacher-feedback.md) to record exploratory
practitioner observations. No real-classroom learning improvement, teacher efficiency gain or
cross-school generalisability is claimed until it has been evaluated.

## Outstanding Nairobi gates

The next steps are repeated real Qwen2.5 3B evaluation, practitioner feedback using fictional
cases, and an offline presentation rehearsal. Before any real learner pilot, verified teacher
authentication, role-based access, privacy safeguards, data retention and appropriate school
approval are required.

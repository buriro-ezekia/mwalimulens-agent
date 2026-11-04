# MwalimuLens Learner Progress Review

The teacher workspace brings longitudinal evidence review, a human decision and the resulting
local audit trail into one responsive browser interface. It uses fictional learner records.

The integrated interface provides **Summary**, **Evidence** and **Decision** section links,
evidence IDs that lead to their source rows, separate assessment/practical-task labels and a
dedicated decision panel. Unscored observations remain visible without becoming zero scores.
Scores from different tasks are not necessarily directly comparable. The narrow-screen layout
keeps record labels and actions readable; the technical audit is expandable.

The [release record](release-status.md) identifies the integrated commit, completed operator
browser checks and remaining release gates.

## Start on Windows

From the released `main` source or the `product-development` checkout, with the project's
virtual environment installed:

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

### Enable local Qwen review

Use a checkout containing the portal integration, with Ollama running locally and
`qwen2.5:3b` already installed:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --enable-qwen --output-dir 'D:\ML-runtime\portal'
```

The flag exposes **Run local Qwen review**. Startup still shows a practice case;
it does not run inference. Selecting the action starts one isolated background
job using real Education MCP retrieval and one bounded local Qwen generation.
This mode does not use the borrowed Filesystem MCP.

| Qwen state | What the workspace shows |
| --- | --- |
| Running | Progress from the current job; case changes and review actions are blocked. Read-only progress requests do not start another generation. |
| Candidate | The validated finding, evidence and existing teacher-decision form; confirmation is still required. |
| Abstention | The model's actual reason, with **0 pending / 0 decisions / 0 profile notes** and no decision form. |
| Error | The actual failure and retained diagnostic files, with no decision form or substituted practice finding. |

Only one Qwen job may run at a time. Duplicate submissions are rejected, and
changing cases invalidates earlier confirmation controls. Each job retains its
own files under a `qwen-*` directory. The [Qwen integration guide](portal-qwen-integration.md)
describes execution limits, audit interpretation and verification requirements.
This mode requires the development integration until it is included in a source
release.

### Reopen a saved Qwen review

Every case shows its mode, case ID and opening context. Default startup creates
a practice case automatically; this does not mean **New practice case** was selected.
Select **Saved Qwen reviews**, then **Open saved review** to return to an existing
job in the same output folder. Opening makes no model request and preserves its
recorded outcome and any simulated teacher decision.

For the operator's existing case, restart directly with:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal' --open-qwen qwen-m1292e06
```

This bypasses practice-case creation and needs neither Ollama nor `--enable-qwen`.
The portal checks the full saved bundle before enabling review. Incomplete or
inconsistent records open with review disabled; nothing is regenerated or repaired.
Use one portal instance per output folder.

## Complete a teacher review

These steps apply to a pending candidate from any of the three modes:

1. Read the evidence summary, chronological records and highlighted counter-evidence.
2. Choose **Approve**, **Revise** or **Reject**.
3. Enter a reason, and revised wording if you selected Revise.
4. Select **Review decision** to inspect the confirmation page. Nothing is saved yet.
5. Select **Confirm simulated decision** to record the outcome, or **Go back without saving**
   to return to the evidence without recording a decision or profile note.
6. Inspect the updated status, synthetic profile-note count and expandable audit trail.
7. Start a separate case using **New practice case**, **Run MCP evidence analysis**
   or, when enabled, **Run local Qwen review**.

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
- Teacher decisions and profile notes go through the existing human-only service method.
  The application may submit a validated pending candidate, but the model cannot call
  `record_teacher_review` or record a teacher decision.
- Qwen jobs require an explicit form submission with a session token and one-use nonce.
  The child uses only local `qwen2.5:3b` at `127.0.0.1:11434`; the browser cannot
  select a remote provider, another model or larger execution limits.
- The browser never sends credentials or learner data to a cloud API.
- The server does not serve arbitrary files or expose a public write endpoint. Local processes
  with access to the same computer are **not** treated as separate trusted users.
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

The Qwen integration requires separate regression coverage for progress, valid candidates,
valid abstentions, failures, duplicate launches and stale confirmations. Tests use mocked
native model responses with genuine MCP access; they do not perform live inference.

Operator screenshots/reports after the UI corrections cover the seeded and genuine deterministic
MCP workflows, all three decisions, cancellation and narrow-screen presentation. The integrated
commit also has hosted quality success. Those observations are recorded in the release record;
they are not pending checks for the already integrated UI. For future behaviour changes, repeat
the relevant browser checks on the intended device. The [final source-release review](final-release-review-2026-11-03.md)
records the release scope; PR #31 records its integration state.

Those completed observations cover the earlier seeded and deterministic modes.
The [4 November portal observation](portal-observation-2026-11-04.md) adds a
Windows abstention screenshot and the matching job/report files. It does not
establish candidate, error or narrow-window acceptance for the Qwen path.
Implementation and regression tests make no live model request.

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
narrow-window observations and their provenance limits. The owner authorised proceeding with
the bounded source release; its [final review](final-release-review-2026-11-03.md) does not
establish model or classroom validity.
The remaining Qwen browser outcomes, consistent real Qwen judgement and practitioner feedback
using fictional cases remain unestablished; any new inference
campaign requires separately authorised bounds. Before any real learner pilot, verified teacher
authentication, role-based access, privacy safeguards, data retention and appropriate school
approval are required.

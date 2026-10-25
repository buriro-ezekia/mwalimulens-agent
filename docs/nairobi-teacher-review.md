# Nairobi teacher-review sandbox (synthetic only)

**Status:** post-selection experimental functionality, not part of the frozen challenge submission.

This separate demonstration exercises the existing human-only EducationToolService.record_teacher_review
path. It does **not** authenticate a teacher, connect to a school database, expose a public endpoint,
or run an LLM. The pending candidate is seeded from fictional L001 / MATH-FRACTIONS evidence
through the existing service, so the review action can be inspected independently of model behaviour.

The original submission remains at commit 6215b9efb79ffd022a835dabba386c5ccb8226e4.
The published 2:39 video remains the authoritative original submission recording.

## Run on Windows

From the nairobi-refinement-2026 branch, with the existing virtual environment:

~~~powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_review_demo
~~~

The command creates a **new** disposable synthetic-state directory under
runtime/nairobi_review_sandbox/review-*/ for each run. The before.html page opens in your
browser, showing the claim, supporting evidence, counter-evidence, uncertainty and the pending
human gate. Return to PowerShell to choose approve, edit, reject or cancel, enter a reason,
and type the exact word REVIEW to confirm. A confirmed decision is recorded through the real
service method, then after.html opens to show the resulting state and audit trail.

To inspect the pending candidate without recording any decision:

~~~powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_review_demo --prepare-only
~~~

For a terminal-only run that prints HTML paths rather than opening a browser:

~~~powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_review_demo --no-open
~~~

You can perform three **independent** runs to demonstrate approve, edit and reject. Each has
its own state file. A rejected candidate creates **zero** profile updates. Approve and edit
create one **synthetic** profile update each; the edit path persists the human's revised wording.
Cancelling or failing to type REVIEW leaves the candidate pending.

## Safety and provenance

- Every learner record in this demonstration comes from the committed synthetic fixtures.
- The reviewer identifier is deliberately simulated-teacher-not-authenticated; this is **not**
  proof of teacher identity or permission.
- There is no HTTP server or browser write form. The browser page is a read-only local HTML view;
  the explicit terminal action invokes the existing Python service method.
- The language model does not see or call record_teacher_review. This sandbox does not change
  the existing model-facing MCP allowlist.
- The candidate is **seeded** for the review demonstration. Do not claim the LLM generated it
  in this run, or that this is a live MCP-client interaction.
- Every run uses a new local state file. No original evidence, challenge evaluation, historical
  failure, submitted video or frozen branch is modified.
- Do not enter real learner information or use this workflow as a production school system.

## Verify

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_teacher_review_demo.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git status --short
~~~

The feature is not fully validated until these commands pass on the intended development
machine and a human has checked the actual browser before/after pages.

## Next gate

For genuine school deployment, teacher authentication, role-based authorisation, data
protection, consent and audit retention must be designed and independently tested. This
sandbox does not satisfy those requirements. The next Nairobi tasks are repeated local Qwen
reliability evaluations and an offline presentation rehearsal.

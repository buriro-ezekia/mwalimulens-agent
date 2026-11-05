# Offline workspace demonstrations

These authored examples let a presenter show candidate review and error handling
without waiting for Qwen. They use the existing fictional evidence and local
review service, with no model inference, MCP client or external assets. They
demonstrate application behaviour, not model reasoning or provider availability.

## Open an example

From a development checkout containing this feature, start the candidate example:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal' --demo candidate
```

Ollama, its model files and the borrowed Filesystem MCP server are not needed for
this path. Keep the terminal open while using the browser. Stop the portal with
**Ctrl+C** before starting another instance in the same output folder.

The workspace identifies the case as **Authored demonstration**, shows its
`demo-*` ID and states that it is not a Qwen result. This disclosure also appears
on the confirmation page and after a decision or reopening. Without
`--enable-qwen`, the browser has no action for launching a model request.

Select **Demonstration cases** beneath the case ID to create either example:

| Example | Starting counts: pending / decisions / notes | Behaviour |
| --- | --- | --- |
| Candidate | 1 / 0 / 0 | An authored, provisional finding enters the existing teacher confirmation flow. |
| Error | 0 / 0 / 0 | A clearly labelled simulated connection failure has no candidate or decision controls. |

The error example can also be opened directly:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal' --demo error
```

Creating a new example reserves a separate directory. GET navigation and browser
refresh do not create a case, launch inference or record a decision. Case changes
are blocked while an explicitly launched Qwen worker is active.

## Show the teacher decision

For a candidate demonstration, select **Revise**. The following wording is an
example for presentation practice; it is not an educator-approved assessment.

**Reason for your decision:**

> I am revising this authored finding to distinguish recorded task scores from independent understanding. EV-008 supports retaining uncertainty and asking a follow-up question.

**Revised wording:**

> Recorded fraction-task scores differ across terms, while independent explanation remains uncertain. Ask the learner to explain their method on an unfamiliar fraction problem without support.

Select **Review decision**. The case ID and authored-example disclosure remain
visible. **Go back without saving** leaves **1 / 0 / 0**. A decision is recorded
only after **Confirm simulated decision**; a confirmed revision shows the
replacement wording and **0 / 1 / 1**. Reusing the confirmation cannot create
another decision or profile note.

Other decisions remain available, each requiring a reason and confirmation:

| Decision | Example reason for this authored case | Confirmed counts |
| --- | --- | --- |
| Approve | I am retaining the provisional description of recorded scores while keeping the uncertainty in EV-008 visible. Independent explanation still needs a follow-up task. | 0 / 1 / 1 |
| Reject | I am rejecting this authored finding because the tasks do not establish comparable performance or independent understanding. Gather further evidence before retaining a profile note. | 0 / 1 / 0 |

## Reopen the same demonstration

On **Demonstration cases**, the saved list shows each example's ID, declared
scenario and creation timestamp. Select **Open demonstration** beside the
required ID. The original fixture and any later simulated human decision are
checked before the saved state is offered for review.

To reopen at startup, substitute the exact ID shown in the browser:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal' --open-demo demo-YOUR-CASE-ID
```

Reopening leaves files unchanged and retains any recorded decision and note
count. A pending candidate still requires confirmation. A resolved candidate
has no new decision form. A case change invalidates earlier confirmation and
model-launch controls. Missing, altered or incompatible records open with review
disabled and counts marked as unverified; the renderer does not read rejected
state. Paths outside the selected output root and linked records are rejected.

The initial-mode options `--demo`, `--open-demo`, `--open-qwen` and
`--initial-mode` are mutually exclusive. An invalid explicit ID does not silently
open a different case. Use one portal instance per output folder.

## Keep the evidence clear

Each demonstration stores `portal_demo.json` and `state.json` under `demo-*`.
The manifest records the authored source, case ID, scenario, zero model requests,
zero MCP client calls and the initial local-service audit. A candidate is created
through the local review service; an error example records only the local
fictional-evidence read. No Qwen report, proposal capture or benchmark pass is
fabricated. Human decisions subsequently update only that example's state.

Actual model attempts remain under `qwen-*`, in **Saved Qwen reviews**, with the
separate `--open-qwen` path. A demonstration cannot be opened as an actual Qwen
result. The real Windows abstention and its successful reopening are recorded in
the [operator observation](portal-observation-2026-11-04.md). Demonstration checks
do not add a live candidate or error observation to that evidence.

## Verification scope

On 4 November 2026, the completed change passed **940 tests in 30.65 s**,
including 57 additional regression cases. Ruff, dependency integrity, whitespace
and all **60 relative documentation-link checks** passed. No live model request
was made.

Self-contained tests cover both authored outcomes, confirmation, cancellation,
all three decision consequences, repeated opening, case identity, unchanged
files, request guards, active-worker blocking and rejected records. Tests forbid
model and MCP subprocesses. These checks establish local record consistency;
reviewer identity remains simulated.

No automated visual acceptance is included in these results. Subsequent operator
screenshots show the desktop catalogue, a confirmed candidate revision, the
authored error and reopening with the retained reason, final wording and one
synthetic profile note. The
[observation record](portal-observation-2026-11-04.md#authored-demonstration-desktop-observations)
identifies their scope and limits. The screenshots do not establish every
intermediate confirmation view or a measured narrow-window layout.

Narrow-window acceptance for these authored examples remains pending. It needs
no model generation and does not repeat the completed offline MCP rehearsal.
Software and desktop checks do not resolve the model's semantic limitations.

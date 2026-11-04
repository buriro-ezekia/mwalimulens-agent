# Local Qwen review in the teacher workspace

The optional portal mode connects the existing structured Qwen workflow to the
teacher interface. It displays progress and the actual candidate, abstention or
error from a fresh local job. It uses fictional evidence and simulated reviewer
identity, with the existing human confirmation required for every decision.

## Start and run

Use a development checkout containing this integration until it reaches a source
release. Install the Python dependencies and `qwen2.5:3b` beforehand, and start
Ollama on its local endpoint. The Qwen path uses Education MCP; it does not need
the borrowed Filesystem MCP or its Node.js server.

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --enable-qwen --output-dir 'D:\ML-runtime\portal'
```

Startup opens the seeded practice case without inference. Select **Run local Qwen
review** to start a job. Without `--enable-qwen`, the portal offers its existing
practice and deterministic MCP modes.

The page shows the current mode, case ID and whether the case opened automatically
at startup or was reopened from saved records. A practice case at startup does
not establish that the user selected **New practice case**.

The launch is an explicit POST protected by the session form token and a one-use
nonce. Only one job per portal session can be active. Duplicate launches are rejected, and case
changes and review actions are blocked while it runs. Progress is read through
local GET requests, which cannot launch inference or submit a candidate. The
interface uses local assets.

## Outcomes

| Outcome | Browser behaviour | Human-review consequence |
| --- | --- | --- |
| Running | Shows the current job's available progress. | No review controls are offered while the job is active. |
| Valid candidate | Opens the actual validated finding, evidence and decision panel. | Starts with one pending candidate. Approve, Revise or Reject still requires the existing confirmation step. |
| Valid abstention | Displays the model's actual abstention reason. | Zero pending candidates, decisions and profile notes; no decision controls. |
| Error | Displays failure information and retains the job's diagnostics. | No decision controls or substituted seeded candidate. |

The browser outcome is distinct from the evaluation rubric. A valid abstention
can fail the benchmark's fixed expected-candidate scenario while remaining a
valid response for the interface to display. The portal does not regrade that
result or turn the absence of a candidate into malformed JSON. It also does not
establish that an abstention reason is educationally sound.

Candidate confirmation remains bound to the current case. A later job or case
change invalidates earlier confirmation controls; an old page cannot confirm a
decision against the new case. Approve and Revise create one synthetic profile
note after confirmation; Reject creates none.

## Bounded execution and authority

Each explicit launch starts an isolated background child using the existing
structured workflow. The application retrieves Education MCP evidence, requests
a decision and submits only a validated candidate. The model does not select or
call action tools in this path. It cannot record a teacher decision or update a
profile.

| Setting | Portal job |
| --- | --- |
| Model | `qwen2.5:3b` |
| Local provider base URL | `http://127.0.0.1:11434/v1`; native structured generation uses `/api/chat` |
| Decision policy | Existing `provisional_review_v2` |
| Format schema | Explicit opt-in `review_decision_outcome_v2` |
| Model request limit | 1 |
| Prewarm / proposal repair | Disabled / no second generation |
| Internal deadline / outer watchdog | 210 s / 240 s |
| Candidate submission | At most one, after validation |

The browser cannot override these settings. The standalone structured CLI keeps
its existing default schema, and this integration does not change prompts or the
semantic policy. Provider-side cancellation remains unverified even when the
local watchdog ends a job.

## Local records

Each job has a separate `qwen-*` directory under the selected output root.
Available files include `portal_job.json`, `evidence_snapshot.json`, `state.json`,
`report.json`, `report.progress.json`, `result.json`, `proposals.json`,
`stdout.txt` and `stderr.txt`. Available progress and unsuccessful attempts remain
inspectable. A failed run is not replaced by a successful practice case.

The `proposals.json` capture contains logical generation inputs and returned raw
output, rather than an exact HTTP request envelope. Current-job evidence and
historical model reports must be identified separately in the technical audit.
See the [structured-workflow contract](structured-review-contract.md) for source
validation, capture and submission rules, and the
[manual semantic rubric](semantic-review-rubric.md) for reasoning assessment.

### Reopen an existing result

Select **Saved Qwen reviews**, then **Open saved review** beside the required ID.
The list is restricted to immediate `qwen-*` folders under the current output
root; its labels are saved metadata, not verified outcomes. Opening checks the
complete records and does not generate a response or change any files. For a
direct restart into the operator's existing case:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal' --open-qwen qwen-m1292e06
```

Replace the ID for another saved job. This option bypasses practice-case creation
and cannot be combined with `--initial-mode`. Neither Ollama nor `--enable-qwen`
is required. The portal requires an explicit choice rather than silently
selecting a different saved attempt.

Completed candidates and abstentions undergo the original proposal, schema,
policy, hash and MCP-audit checks. Saved evidence must match the current fictional
fixture. A later simulated teacher decision is checked against the generation
record, human audit and profile-note consequence. A pending candidate still needs
confirmation; a resolved candidate displays its existing decision without adding
another note. Changing cases clears earlier confirmations and launch nonces.

Missing, inconsistent, incompatible, interrupted or failed records open with an
error and no review controls. They are retained on disk. Reopening cannot attach
to or resume an old worker, and it makes no claim about provider-side cancellation.
Use one portal instance per output folder; concurrent writers are unsupported.
These are local consistency checks, not authenticated reviewer identity or proof
of model reasoning quality. Linked job folders and artefacts are rejected.

## Authored presentation examples

The workspace also offers separate authored candidate and error demonstrations,
through **Demonstration cases**, `--demo candidate` and `--demo error`. These
examples make zero model requests and no MCP client calls. They retain their
authored disclosure on confirmation and result pages and use separate `demo-*`
records, reopened with `--open-demo`. They cannot be opened as actual Qwen results.
See the [demonstration guide](workspace-demonstrations.md) for sample reasons,
revised wording and expected counts. These checks demonstrate the application
workflow and do not add live-model acceptance evidence.

## Verification scope

Integration tests use mocked native Qwen responses with genuine Education MCP
access. Required cases cover progress, a validated candidate entering the human
review flow, a valid abstention, execution and validation failures, repeated
launches, blocked actions during a job and stale confirmations. Tests must also
check that GET requests, startup and ordinary practice navigation do not perform
inference.

On 4 November 2026, the integration passed **848 tests in 32.27 s**, Ruff,
dependency integrity and whitespace checks. All **48 relative Markdown links**
in the changed documentation resolved. New coverage includes 33 backend cases
using the structured controller with genuine in-process MCP and mocked native
responses, and 30 HTTP/CLI cases using controlled jobs and real synthetic review
state. No live Qwen request was made during implementation or these tests.

Independent source review identified and verified corrections for cleanup races,
unconfirmed worker termination, missing progress when no browser poll occurred,
and thread-start failure. Replacement launches remain blocked while an owned
worker is active, even if the attempt has an error outcome.

Automated visual inspection was blocked by this session's browser policy. No
desktop or narrow-window visual pass is claimed for this new path. An
operator-supplied Windows abstention screenshot and matching job/report files are
now recorded in the [portal observation](portal-observation-2026-11-04.md).
The operator subsequently confirmed Windows reopening of that same saved
abstention, with the correct case ID and zero decision/profile counts; the dated
record identifies both reopening screenshots.
Candidate, error and narrow-window acceptance for the Qwen path remain unverified
on the intended device; earlier seeded and deterministic MCP rehearsals do not
cover them. No additional inference is required to inspect or reopen saved files.
The development pull request records the exact published head and hosted checks.

Saved-review reopening and case identity subsequently passed **883 tests in
35.51 s**, Ruff, dependency integrity and whitespace checks, with **54 relative
documentation links** resolving. The 35 additional regression cases cover
read-only reopening, candidates and abstentions, retained human decisions,
inconsistent or missing records, fixture drift, path restrictions, form tokens,
busy-worker rejection, stale confirmations and direct CLI reopening. These
checks used no live model and establish no new visual acceptance result.
Rejected saved records are not read again by the renderer; their counts are
shown as unverified. Redirected directories are rejected even when their
destination lies within the output root, covering Windows junction behaviour.

Hosted build #135 stopped before tests when GitHub refused CircleCI's SSH
checkout key. The public repository's CI now fetches the exact `CIRCLE_SHA1`
over HTTPS; the Python, dependency, npm, pytest and Ruff gates remain in place.
CircleCI's [configuration reference](https://circleci.com/docs/reference/configuration-reference/#checkout)
documents why HTTPS checkout uses a custom command. The development pull request
records subsequent hosted results separately from this infrastructure failure.

Connecting the workflow to the interface does not resolve the recorded model
reasoning limitations or establish classroom suitability. The
[4 November saved observation](semantic-validation-2026-11-04.md) and
[policy/rubric review](policy-rubric-alignment.md) retain their own evidence and
limits.

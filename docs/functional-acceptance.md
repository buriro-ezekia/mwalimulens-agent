# Product functional acceptance

The MwalimuLens teacher workflow is evaluated independently of the original
challenge video. All acceptance cases use fictional learner records, local JSON
state and a **simulated** reviewer identity; no real learner data is permitted.

## Recorded acceptance

The [release record](release-status.md) separates earlier operator-reported service/MCP
acceptance, the 727-test UI baseline, hosted quality and later browser observations.
Seeded Approve, Revise/Edit and Reject, plus genuine deterministic MCP acceptance, were
reported as PASS with exit 0. The UI walkthrough after the browser corrections was also
reported as completed. Their local JSON, logs and screenshots have not been committed.

These are completed checks within their recorded scopes. The commands below reproduce them
when behaviour changes; no additional acceptance or model run is required merely to reconcile
documentation. The actual disconnected-network rehearsal remains separate and outstanding.

## Automated teacher decisions

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.product_acceptance --output-dir 'D:\ML-runtime\acceptance'
```

The runner creates three isolated cases: Approve, Revise and Reject. It checks
that supporting and counter-evidence are present, that the candidate begins
pending human review and that the decision is audited. Reject creates zero
profile updates; approve/revise create one synthetic note each. The runner
stores a JSON report under `runtime/product_acceptance/`.

This is a **service-level acceptance check**. It does not replace the HTTP
interaction tests in `tests/test_teacher_portal.py` or a human review of the
interface in a browser.

## Genuine MCP acceptance

To execute the same acceptance checks and add a real Education/Filesystem MCP
tool workflow through the existing deterministic agent:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.product_acceptance --with-mcp --output-dir 'D:\ML-runtime\mcp-acceptance'
```

This requires the pinned Node.js MCP dependency. It verifies the Education MCP
evidence read, the borrowed Filesystem MCP reference read, the pending-candidate
action and the untouched human gate before teacher review. Errors are reported
as failures, not hidden. This mode **does not perform Qwen inference**.

## Real-model timing and reliability

Real inference is a separate, bounded evaluation task, not a prerequisite for the
seeded or deterministic MCP checks. Inspect the plan without inference:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --dry-run
```

Only run a campaign after its request/time bounds have been authorised. Inspect every
attempt under `runtime/model_reliability/`, including failures and timeouts. That
harness repeats one fictional learner task; the separate [four-scenario protocol](multi-scenario-evaluation.md)
covers candidate and abstention cases. Neither establishes classroom generalisability.
The completed native outcome-schema compatibility probe is not a passing semantic
evaluation and need not be repeated for release documentation.

## Browser verification

Start the local application:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal'
```

In the browser, run a new fictional case and verify Approve, Revise and Reject
on separate attempts. Check reason entry, confirmation, evidence highlights,
audit details, one-use confirmation, profile-note counts and readability at
desktop and narrow-screen sizes. Verify **Go back without saving** leaves the case
pending with no decision or profile note. Then choose **Run MCP evidence analysis**,
inspect the genuine tool audit and repeat the decision workflow. The interface shows
Summary, Evidence and Decision links, with technical records under **Technical evidence
and audit trail**. Keep assessment and practical-task scores distinct.

The browser is a local demonstration, not an authenticated school portal.

## CircleCI push-trigger verification

Hosted quality has already reported success for the integrated UI commit at
[CircleCI #118](https://circleci.com/gh/buriro-ezekia/mwalimulens-agent/118).
For a new change, inspect the result associated with the **new** commit SHA.
Verify the pipeline event separately before claiming a repository-push trigger
rather than a manual/API run. A commit status alone does not establish that mechanism.

Only report CI automatic triggering as verified after this newer push appears
without manually selecting `Trigger pipeline`.

## Reporting rule

Record each result separately: local pytest, Ruff, service acceptance,
genuine MCP acceptance, real Qwen timing and hosted CI. A successful
deterministic test cannot stand in for a real-model run or practitioner
validation.

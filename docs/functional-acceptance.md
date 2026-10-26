# Product functional acceptance

The MwalimuLens teacher workflow is evaluated independently of the original
challenge video. All acceptance cases use fictional learner records, local JSON
state and a **simulated** reviewer identity; no real learner data is permitted.

## Automated teacher decisions

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.product_acceptance
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
.\.venv\Scripts\python.exe -m mwalimulens.product_acceptance --with-mcp
```

This requires the pinned Node.js MCP dependency. It verifies the Education MCP
evidence read, the borrowed Filesystem MCP reference read, the pending-candidate
action and the untouched human gate before teacher review. Errors are reported
as failures, not hidden. This mode **does not perform Qwen inference**.

## Real-model timing and reliability

Once local Ollama and `qwen2.5:3b` are available, measure actual repeated
inference separately:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --dry-run
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --runs 3 --timeout 600
```

Inspect every attempt under `runtime/model_reliability/`, including failures
and timeouts. The current harness repeats one fictional learner task, so its
results must not be generalised to other classrooms, languages or curricula.

## Browser verification

Start the local application:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal
```

In the browser, run a new fictional case and verify Approve, Revise and Reject
on separate attempts. Check reason entry, confirmation, evidence highlights,
audit details, one-use confirmation, profile-note counts and readability at
desktop and narrow-screen sizes. Then choose `Run MCP evidence analysis`,
inspect the genuine tool audit and repeat the decision workflow.

The browser is a local demonstration, not an authenticated school portal.

## CircleCI push-trigger verification

After the acceptance script and tests are committed, inspect CircleCI's
pipelines for a new run on `product-development` associated with the **new**
commit SHA. Verify whether its trigger event is a repository push rather than
a manual/API run. A successful prior pipeline does not establish that automatic
triggering has been configured.

Only report CI automatic triggering as verified after this newer push appears
without manually selecting `Trigger pipeline`.

## Reporting rule

Record each result separately: local pytest, Ruff, service acceptance,
genuine MCP acceptance, real Qwen timing and hosted CI. A successful
deterministic test cannot stand in for a real-model run or practitioner
validation.

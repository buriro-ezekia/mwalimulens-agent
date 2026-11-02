# MwalimuLens

**Evidence-led learner progress review**

MwalimuLens helps teachers review learning evidence across school terms. It brings
assessment results, practical work and classroom observations into one workspace,
with supporting records, counter-evidence and uncertainty kept alongside each
provisional finding. The teacher decides whether to retain, revise or reject it.

The project began in the **Education — The Long View** track of the African Agentic
AI Design Challenge, with longitudinal strength tracking as its central focus.
Development continues as a local prototype using fictional learner records. It is
not a validated school information system, and its reviewer identity is simulated
rather than authenticated.

## What the workspace provides

The Learner Progress Review workspace presents the current finding, its supporting
records and the observations that qualify it. Recorded scores remain separate from
judgements about mastery. Evidence identifiers connect a finding to the relevant
rows, while the teacher's decision requires a rationale and a confirmation step.

Each practice case has its own local state and audit trail. Approve and Revise
create one synthetic profile note after confirmation; Reject creates none. A
pending finding does not update a learner profile, and the model cannot approve
its own work.

### Three distinct execution paths

| Path | What happens | Model inference |
| --- | --- | --- |
| Practice case | A seeded fictional finding opens directly in the teacher workspace. | None |
| MCP evidence analysis | Deterministic orchestration calls the Education MCP and read-only Filesystem MCP servers, then prepares a finding for review. | No Qwen inference |
| Local model evaluation | Qwen2.5 3B runs through local Ollama under the evaluation workflow. | Real local inference |

These paths serve different purposes. A successful practice case or deterministic
MCP run does not establish the quality or reliability of a model's educational
judgement. Previously committed model results appear separately in the technical
audit section; they are not presented as new inference in the browser session.

### Fast judge demo

The original fast judge demo uses a deterministic local model to demonstrate the
Education MCP and borrowed Filesystem MCP calls with fictional evidence. It is not
presented as the open-weights evidence. The real Qwen2.5 3B run is documented
separately in `evidence/open_weights_run.json`, rather than being attributed to the
scripted demonstration. See [the demonstration guide](docs/demo-guide.md) for the
original sequence and presentation requirements.

## Getting started

Use Python **3.11 or newer**. Genuine Filesystem MCP calls also require Node.js
**20 or newer** and npm. Ollama and the `qwen2.5:3b` model are needed only for the
separate real-model workflow, not for opening a practice case.

The commands below use PowerShell. A short checkout and short runtime directory
are preferable on Windows, particularly when a workflow creates nested case and
report folders.

### Install the development build

```powershell
git clone --branch product-development https://github.com/buriro-ezekia/mwalimulens-agent.git D:\MwalimuLens
Set-Location 'D:\MwalimuLens'

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm.cmd ci --no-audit --no-fund
```

Complete dependency installation while connected to the internet. Do not replace
an existing checkout or discard local work merely to use the example path.

### Open the teacher workspace

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal'
```

The application opens a browser at a local `127.0.0.1` address. Keep its PowerShell
window running while using the workspace; press **Ctrl+C** to stop it. The first
page is a practice case and does not call Ollama. Select **Run MCP evidence
analysis** to start a separate deterministic case using genuine MCP calls.

The interface uses local styles and system fonts rather than external assets.
Offline operation still needs to be checked on the intended device after all
required dependencies have been installed.

## Reviewing a case

Read the provisional finding and its uncertainty before choosing a decision.
Follow the evidence identifiers to inspect the underlying records, including
counter-evidence. Assessment and practical-task scores are labelled separately;
their percentages should not be treated as directly comparable without considering
the tasks and conditions.

Choose **Approve**, **Revise** or **Reject**, and explain the decision. Revise also
requires replacement wording. Select **Review decision** to inspect the
confirmation page. Nothing is recorded until **Confirm simulated decision** is
selected. **Go back without saving** returns to the case without recording a
review.

After confirmation, inspect the decision, final wording and synthetic profile-note
count. Start a **New practice case** for an independent example. Technical tool
activity and previously committed model evidence remain available in the
expandable audit section.

## Technical design

The Python domain layer loads the fictional learner fixtures and orders evidence
by event chronology. The Education MCP service provides evidence retrieval and
provisional-review operations, with a separate human-review method. Local JSON
state records candidates, decisions, profile notes and tool activity.

PydanticAI orchestrates model and tool interactions. FastMCP client tooling limits
the model-visible tool set. The borrowed
`@modelcontextprotocol/server-filesystem@2026.8.31` server provides read-only access
to the reference material in `data/reference/`.

```text
Fictional learner records
        |
        v
Evidence retrieval and provenance checks
        |
        v
Provisional finding or abstention
        |
        v
Teacher review and explicit confirmation
        |
        v
Audited decision and any authorised synthetic note
```

### Tool and review boundaries

| Operation | Authority |
| --- | --- |
| `get_learner_timeline` | Read-only learner evidence retrieval |
| `get_competency_evidence` | Read-only competency evidence retrieval |
| `flag_pattern_for_review` | Create a provisional finding pending teacher review |
| `record_teacher_review` | Human-review path only; excluded from the model-visible allowlist |

The model must not rank learners, assign permanent labels or choose educational
pathways. It cannot record a teacher decision or independently change a learner
profile. The local browser uses a session form token, Host/Origin checks and a
one-use confirmation, but these controls do not provide verified teacher identity
or multi-user authorisation.

### Structured decisions

The opt-in structured-review workflow separates interpretation from submission.
The application retrieves a complete evidence snapshot, requests a structured
candidate or abstention and validates the response before submitting a candidate
through MCP. Required fields, evidence membership, distinct evidence roles and
cross-term support remain runtime checks.

`review_decision_v1` remains the default schema. The optional
`review_decision_outcome_v2` schema expresses the existing candidate/abstention
field dependencies more precisely. Schema validity is not a judgement of
educational correctness. The decision policy, `provisional_review_v2`, permits a
qualified description of recorded evidence without requiring a claim of durable
improvement or independent mastery. Genuine abstention remains possible.

See the [structured-review contract](docs/structured-review-contract.md) and
[decision-schema contract](docs/decision-schema-contract.md) for budgets,
validation, provenance and limitations.

## Verification

Run the software checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

Keep the command outputs and the exact Git commit together. The
[CircleCI pipeline](.circleci/config.yml) runs dependency installation, the test
suite and Ruff in a Linux Python/Node environment. Its results complement, rather
than replace, checks on the intended Windows device.

### Functional and offline acceptance

```powershell
# Independent seeded Approve, Revise and Reject checks.
.\.venv\Scripts\python.exe -m mwalimulens.product_acceptance --output-dir 'D:\ML-runtime\acceptance'

# Seeded checks plus genuine deterministic Education and Filesystem MCP calls.
.\.venv\Scripts\python.exe -m mwalimulens.product_acceptance --with-mcp --output-dir 'D:\ML-runtime\mcp-acceptance'

# Installed prerequisites and a fresh deterministic MCP case; no model check.
.\.venv\Scripts\python.exe -m mwalimulens.offline_preflight --run-mcp --output-dir 'D:\ML-runtime\preflight'
```

Each run retains its report in a new case directory. `automated_pass` confirms the
listed automated checks; it does not prove that internet connectivity was
intentionally disconnected or that a person completed the browser workflow.
Follow the [functional acceptance guide](docs/functional-acceptance.md) and
[offline rehearsal checklist](docs/offline-demo.md) for those observations.

### Model evaluation

Real Qwen evaluation is separate from interface and service testing. The
[four-scenario protocol](docs/multi-scenario-evaluation.md) covers longitudinal
patterns, conflicting evidence, a single assessment and missing competency
evidence. The [repeatability harness](docs/model-reliability.md) records independent
attempts, failures, timeouts and timings.

Plan and authorise live inference separately, with explicit request and time
limits. Retain unsuccessful attempts. Report first-pass behaviour separately from
corrected outcomes and distinguish model reasoning from actions prevented by
application safeguards. The project has not established consistent educational
judgement across the four fictional scenarios or generalisability to real schools.

## Evidence and reproducibility

The original challenge submission is identifiable at commit
`6215b9efb79ffd022a835dabba386c5ccb8226e4`. Its recording and evidence remain distinct
from subsequent product development.

| Record | Purpose |
| --- | --- |
| `evidence/open_weights_run.json` | Previously recorded local Qwen run |
| `evidence/borrowed_mcp_run.json` | Borrowed Filesystem MCP verification |
| `evidence/challenge_run.json` | Original combined challenge run |
| `evidence/evals_run.json` | Original evaluation record, including preserved failures |
| `evidence/failures/` | Historical model limitations and unsuccessful attempts |
| `runtime/` or a chosen output directory | Local development and acceptance artefacts |

The original evaluation record distinguishes 11 passing cases from two preserved
historical failures. Do not overwrite those failures or interpret a historical
single-task result as a current reliability estimate.

The [original demonstration video](https://youtu.be/Zh9V_Ptc4ME) and
[reproduction guide](docs/reproducible-run.md) document the challenge workflow.
The original one-command challenge run is:

```powershell
python scripts/run_challenge.py
```

This command includes real model execution and requires its documented local
prerequisites. It is not required to open the teacher workspace or complete the
seeded and deterministic MCP acceptance checks.

## Limitations and responsible use

This is a single-user, synthetic-data prototype. The reviewer identifier is
`simulated-teacher-not-authenticated`; no verified teacher account, school role or
permission is established by the browser session. Do not expose the local server
as a public school service or enter real learner records.

The fictional evaluation set is small. Neither successful software tests nor a
valid model response establishes learning benefit, teacher efficiency or
educational suitability. Practitioner feedback, broader evaluation and explicit
school governance remain necessary before any classroom pilot. Real-learner use
also requires verified identity, role-based authorisation, appropriate consent,
secure persistence, data minimisation and retention arrangements.

## Project guide

| Location | Contents |
| --- | --- |
| `src/mwalimulens/teacher_portal.py` | Local teacher workspace and confirmation flow |
| `src/mwalimulens/domain/` | Learner and longitudinal-evidence model |
| `src/mwalimulens/mcp_server/` | Evidence service, review operations and audit state |
| `src/mwalimulens/agent/` | Orchestration, retrieval, validation and Ollama integration |
| `data/synthetic/` | Fictional learner fixtures |
| `data/reference/` | Read-only educational reference material |
| `tests/` | Contract, workflow, safety and presentation regression tests |
| `docs/` | Architecture, evaluation, acceptance and operating guides |

Further guidance: [architecture](ARCHITECTURE.md), [evaluation](EVALS.md),
[teacher workspace](docs/teacher-workspace.md),
[Education MCP](docs/education-mcp.md),
[borrowed Filesystem MCP](docs/borrowed-filesystem-mcp.md),
[teacher feedback](docs/teacher-feedback.md),
[CPU inference](docs/ollama-performance.md),
[request-sequence analysis](docs/request-sequence-optimisation.md) and
[workflow timing](docs/workflow-timing.md).

## Licence

MwalimuLens is licensed under the [Apache License 2.0](LICENSE).

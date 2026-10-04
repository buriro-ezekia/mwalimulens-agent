# MwalimuLens

> **The agent identifies patterns. The teacher decides what they mean.**

MwalimuLens is an evidence-grounded educational agent built for the **Education — The Long View**
track of the African Agentic AI Design Challenge. It focuses on **longitudinal strength tracking**:
helping a teacher see how learner evidence changes across terms without turning a single score into
a permanent label.

The challenge build uses synthetic learner data only.

## Why this exists

A teacher may have quiz scores, practical work, attendance records and classroom observations
spread across several terms. A simple dashboard can show those records, but it may still leave the
teacher to notice patterns by hand.

MwalimuLens retrieves the relevant evidence, keeps it in event chronology, looks for supporting and
counter-evidence, and produces a cautious candidate pattern for review. It does not decide that the
candidate is true. That decision remains with the teacher.

## What the agent can and cannot do

The model can:

- retrieve a learner timeline;
- retrieve evidence for a specific competency;
- compare evidence across terms;
- cite concrete evidence IDs;
- preserve uncertainty and counter-evidence; and
- submit a candidate pattern as `pending_teacher_review`.

The model cannot:

- call `record_teacher_review`;
- approve, edit or reject its own candidate;
- create a learner-profile update on its own;
- rank learners against classmates; or
- assign a permanent label, pathway, career or subject track.

The human review boundary is enforced in code, not left to prompt wording.

## Fast judge demo

After cloning the repository, the quickest recording-friendly demo is:

```powershell
python scripts/run_demo.py
```

The command prepares the local environment, runs a short real MCP workflow and opens a
self-contained browser page. The fast demo uses a deterministic local model so the video can show
the MCP sequence without waiting several minutes for Qwen.

The page shows:

1. the synthetic L001 / MATH-FRACTIONS evidence timeline;
2. the actual Education MCP evidence call;
3. the actual read-only borrowed Filesystem MCP call;
4. the actual `flag_pattern_for_review` action;
5. the supporting and counter-evidence behind the candidate;
6. the human review gate, with zero teacher decisions and zero profile updates; and
7. the separately committed **real Qwen2.5 3B** validation result.

The deterministic demo is **not** presented as the open-weights evidence. The real Qwen run is
stored separately in `evidence/open_weights_run.json`.

A timed recording guide is in `docs/demo-guide.md`.

## Full reproducible challenge run

For the complete local validation path:

```powershell
python scripts/run_challenge.py
```

External prerequisites are:

- Python 3.11 or newer;
- Node.js 20 or newer with npm;
- a locally running Ollama service; and
- `qwen2.5:3b` installed in Ollama.

The bootstrap creates or reuses `.venv`, installs MwalimuLens, installs the exact npm dependency
graph with `npm ci`, then runs the real open-weights task, the borrowed MCP smoke and the
13-case evaluation suite.

A passing real run is committed at `evidence/challenge_run.json`.

## Current evidence

| Area | Result | Inspectable evidence |
|---|---|---|
| Custom Education MCP | PASS | Four implemented tools and audited state |
| Open-weights model | PASS | `evidence/open_weights_run.json` — Qwen2.5 3B |
| Borrowed MCP | PASS | `evidence/borrowed_mcp_run.json` |
| Evaluation suite | PASS | `evidence/evals_run.json` |
| One-command workflow | PASS | `evidence/challenge_run.json` |
| Historical model failures | Preserved | `evidence/failures/` |
| Under-three-minute video | Ready to record | `docs/demo-guide.md` |

The evaluation report contains **11 current PASS cases and 2 preserved historical FAIL cases**.
Those failures are intentionally retained rather than rewritten after later fixes.

## Architecture

```text
Synthetic learner evidence
        |
        v
Custom Education MCP
  get_learner_timeline
  get_competency_evidence
  flag_pattern_for_review
  record_teacher_review  <-- human path only
        |
        v
PydanticAI orchestrator
        |
        +----> local Qwen / Ollama
        |
        +----> official Filesystem MCP
               read-only, sandboxed
        |
        v
Evidence-grounded candidate
        |
        v
PENDING TEACHER REVIEW
        |
        v
Approve / Edit / Reject
```

The detailed design and boundaries are documented in `ARCHITECTURE.md`.

## MCP boundaries

### Custom Education MCP

| Tool | Purpose | Model-visible |
|---|---|---|
| `get_learner_timeline` | Retrieve ordered learner evidence | Yes |
| `get_competency_evidence` | Retrieve evidence for one competency | Yes |
| `flag_pattern_for_review` | Persist a provisional candidate | Yes |
| `record_teacher_review` | Record approve/edit/reject and any human-approved consequence | **No** |

### Borrowed Filesystem MCP

MwalimuLens reuses the official
`@modelcontextprotocol/server-filesystem@2026.8.31` package for generic local reference-file
access. The model sees only six read-only tools, and the server is sandboxed to `data/reference/`.

This keeps generic filesystem infrastructure out of the custom Education MCP while preserving an
auditable boundary between reference material and learner evidence.

## Evaluation

`EVALS.md` documents 13 cases covering:

- late-entered evidence;
- conflicting quantitative and qualitative evidence;
- missing-term gaps;
- insufficient longitudinal history;
- one-off anomalies;
- evidence-ID and competency validation;
- teacher approve/edit/reject consequences;
- the model-facing tool boundary;
- borrowed-MCP read-only behaviour;
- the successful real Qwen workflow; and
- preserved genuine model failures.

Run the deterministic suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Repository guide

```text
data/synthetic/          fictional learner evidence used by the challenge
data/reference/          classroom reference material; not learner evidence
src/mwalimulens/domain/  validated longitudinal data model
src/mwalimulens/mcp_server/
                         custom Education MCP and local audit/review state
src/mwalimulens/agent/   orchestration, Ollama and borrowed-MCP integration
evidence/                promoted judge-inspectable run evidence
tests/                   deterministic contract, safety and reliability tests
scripts/                 clean-checkout challenge and demo entry points
```

## Limitations

MwalimuLens is a challenge prototype, not a validated production decision system.

- The committed learner records are synthetic.
- The evaluation set is deliberately small.
- The fast browser demo uses deterministic orchestration for recording speed.
- The real open-weights evidence comes from a separate local Qwen2.5 3B run.
- The project does not establish educational validity across real schools, curricula, languages or
  learner populations.
- A candidate pattern is not a diagnosis, classification or permanent learner profile.

These limits are intentional. The project is designed to make uncertainty and human responsibility
visible rather than hide them.

## Further documentation

- `ARCHITECTURE.md` — system design and decision boundaries
- `EVALS.md` — evaluation cases and preserved failures
- `docs/education-mcp.md` — custom MCP contract
- `docs/agent-orchestrator.md` — model-facing tool boundary
- `docs/borrowed-filesystem-mcp.md` — borrowed server rationale and read-only boundary
- `docs/open-weights-run.md` — local Qwen workflow
- `docs/reproducible-run.md` — clean-checkout validation path
- `docs/demo-guide.md` — recording workflow
- `docs/submission-readiness.md` — final repository audit

## Challenge and licence

Official Education track:
https://agentic-africa-challenge.lovable.app/tracks/education

Submission timing and repository evidence are tracked in
`docs/challenge-requirements.md`.

MwalimuLens is licensed under the **Apache License 2.0**.

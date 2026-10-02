# MwalimuLens

> The agent identifies patterns. The teacher decides what they mean.

MwalimuLens is an evidence-grounded educational agent for the **Education — The Long View**
track of the African Agentic AI Design Challenge.

Its selected theme is **longitudinal strength tracking**: connecting evidence across terms and
years so a teacher can inspect defensible patterns that may be invisible in a single term.

## Product boundary

MwalimuLens is decision support, not an autonomous learner-classification system.

The challenge build is designed so that:

- every claimed learner pattern cites source evidence;
- supporting and counter-evidence remain visible;
- uncertainty is explicit;
- the agent never ranks learners against classmates;
- the agent never autonomously assigns a learner label, track, career or subject pathway; and
- consequential profile changes require an explicit teacher review.

## Planned challenge stack

- **Custom MCP server:** longitudinal learner evidence and bounded review actions
- **Borrowed MCP server:** official Model Context Protocol Filesystem MCP, read-only and sandboxed
- **Orchestration:** open-source Python orchestration
- **Open-weights model:** local Qwen through Ollama
- **Data:** synthetic learner records only
- **Evaluation:** longitudinal, adversarial and human-gate cases

## Repository status

Implemented in the current codebase:

- the challenge contract and human-decision boundary;
- a typed longitudinal learner/evidence domain;
- deterministic chronology and competency retrieval;
- synthetic multi-term fixtures containing late entry, missing records, conflicting evidence,
  a one-off anomaly and an insufficient-history case; and
- a custom Education MCP server with four tools, structured outputs and tool-call auditing;
- a bounded `pending_teacher_review` action; and
- an explicit teacher approve/edit/reject gate that records reviewer identity and permits profile
  updates only after approve/edit decisions; and
- a PydanticAI orchestrator whose MCP toolset exposes only evidence retrieval and
  `flag_pattern_for_review` to the model; and
- a local Qwen/Ollama provider plus an executable open-weights challenge task and JSON evidence
  report; and
- an official borrowed Filesystem MCP integration restricted to read-only classroom-reference
  access, with borrowed calls written to the same audit stream; and
- a reproducible 13-case evaluation suite covering messy longitudinal data, human-gate
  invariants, borrowed-MCP safety, current real-model success and preserved model failures.

A real local Qwen2.5 3B run has passed all open-weights evidence and safety checks and is
committed at `evidence/open_weights_run.json`. The official borrowed Filesystem MCP has also
passed its real read-only smoke run, with promoted evidence committed at
`evidence/borrowed_mcp_run.json`. The user interface remains unfinished.

## Run the custom Education MCP server

For a clean Windows setup, use the repository-local virtual environment so CLI executables stay
on the active environment PATH:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m mwalimulens.mcp_server.server
```

The server uses stdio by default and writes runtime audit/review state to
`runtime/education_mcp_state.json`.

See `docs/education-mcp.md` for the tool contract, `docs/agent-orchestrator.md` for the
model-facing allowlist boundary, `docs/open-weights-run.md` for the local Qwen validation
workflow, `docs/borrowed-filesystem-mcp.md` for the borrowed-server boundary and rationale, and
`EVALS.md` for the reproducible reliability evaluation matrix.

## Development workflow

Feature work is developed on a branch, reviewed in a pull request, tested locally, and only then
merged to `main`.

GitHub Actions may be unavailable because of repository/account budget limits. A failed or
unstarted hosted workflow is therefore not treated as a product defect unless its logs show an
actual code or test failure. Local test output is the authoritative validation evidence during
development.

## Official challenge source

Education track: https://agentic-africa-challenge.lovable.app/tracks/education

The public track page currently shows a **15 October 2026** deadline. Its detailed rules still
leave the exact submission-period timestamp as TBC, so this project targets completion before
15 October rather than assuming a final-hour cutoff.

## Licence

Apache-2.0.

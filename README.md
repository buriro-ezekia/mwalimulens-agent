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
- **Borrowed MCP server:** an external/official MCP capability, documented before integration
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
- a custom Education MCP server with three tools, structured outputs, tool-call auditing and a
  bounded `pending_teacher_review` action.

Agent orchestration, Ollama/Qwen integration, the borrowed MCP server, teacher approve/edit/reject
persistence and the user interface are **not implemented yet**. This README will not claim those
capabilities until corresponding code and tests exist.

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

See `docs/education-mcp.md` for the tool contract and MCP Inspector command.

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

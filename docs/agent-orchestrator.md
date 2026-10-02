# Agent orchestrator

MwalimuLens uses PydanticAI 2.51.x as its open-source orchestration layer.

The MCP client dependency is constrained to `fastmcp-slim[client]>=4,<5`. FastMCP 4 is the
line compatible with the MCP SDK v2 generation used by MwalimuLens; an older full FastMCP 3.x
installation should not be mixed into the project environment.

## Tool boundary

The Education MCP server itself exposes four tools:

1. `get_learner_timeline`
2. `get_competency_evidence`
3. `flag_pattern_for_review`
4. `record_teacher_review`

The agent does **not** receive all four.

The PydanticAI `MCPToolset` is wrapped with a model-facing filter. The agent allowlist is exactly:

```text
get_learner_timeline
get_competency_evidence
flag_pattern_for_review
```

`record_teacher_review` is filtered before PydanticAI constructs the model request. This is a
code-level boundary rather than an instruction asking the model to behave.

## Human decision boundary

The agent may retrieve evidence and persist a candidate as `pending_teacher_review`.

It cannot:

- approve, edit or reject the candidate;
- create a learner-profile update;
- call `record_teacher_review`; or
- bypass the teacher-review persistence gate.

Teacher decisions remain a separate human path.

## Agent instructions

The current orchestrator instructs the model to:

- retrieve evidence before making a learner-pattern claim;
- cite concrete evidence IDs;
- actively look for counter-evidence;
- state uncertainty;
- avoid turning a single score into a persistent trait;
- abstain when longitudinal history is insufficient;
- never rank the learner against classmates; and
- submit defensible candidates for teacher review rather than making the decision itself.

The tool filter is authoritative even if future prompts or model outputs conflict with these
instructions.

## Runtime connection

PydanticAI connects to the custom Education MCP server through stdio using the same Python
interpreter as the application.

For isolated tests and demo runs, the orchestrator passes:

```text
MWALIMULENS_DATA_DIR
MWALIMULENS_STATE_PATH
```

to the MCP subprocess. This keeps synthetic evidence and runtime workflow state separable between
runs.

## Current model status

The orchestration layer is model-independent. Tests use PydanticAI's local `TestModel` and
`FunctionModel` so no external model or API key is required.

Local Qwen/Ollama integration is now implemented in the model layer. The challenge requirement is
still not claimed complete until the real task produces a passing report and that report is
promoted into `evidence/open_weights_run.json`.

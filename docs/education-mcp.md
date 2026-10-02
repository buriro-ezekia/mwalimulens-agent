# Education MCP server

MwalimuLens uses the official Python MCP SDK v2 and targets the MCP 2026-07-28 protocol revision.

The server is intentionally small. It exposes exactly four custom tools:

| Tool | Type | Behaviour |
|---|---|---|
| `get_learner_timeline` | Read | Returns one learner's evidence in event chronology |
| `get_competency_evidence` | Read | Returns evidence for one learner competency |
| `flag_pattern_for_review` | Action | Persists a candidate as `pending_teacher_review` |
| `record_teacher_review` | Human action | Records approve/edit/reject with reviewer identity |

## Human boundary

`flag_pattern_for_review` is an action because it changes durable workflow state, but it is
deliberately reversible and non-consequential. It does **not** approve a claim, alter a learner
profile, assign a learner label or choose a pathway.

`record_teacher_review` is the human decision gate. Approve preserves the candidate claim,
edit requires teacher-authored replacement wording, and reject creates no profile update.

There is no separate profile-update MCP tool. A profile update can only be created internally by
a successful approve/edit teacher review, making the human gate structural rather than prompt-only.

## Audit trail

Every tool invocation that reaches the MwalimuLens service is audited. This includes successful
calls and domain-validation failures. MCP protocol/schema rejection that occurs before the tool
function starts is handled by the SDK rather than this application audit layer.

Each service-level audit record contains:

- call ID;
- tool name;
- inputs;
- output when successful;
- error type/message when unsuccessful;
- status; and
- timestamp.

The successful `flag_pattern_for_review` action writes its pending-review record and audit event
to the same local JSON state document in one atomic replacement. Teacher review resolution,
the named review record, any approved/edited profile update and the review tool audit are also
persisted together atomically.

By default runtime state is written to:

```text
runtime/education_mcp_state.json
```

The `runtime/` directory is ignored by Git.

## Run locally

Use the repository-local virtual environment on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m mwalimulens.mcp_server.server
```

Using an activated `.venv` also keeps the installed `mcp.exe` and related CLI scripts on the
current shell PATH without modifying the user's global PATH.

The default transport is stdio, which is the official SDK's local-server transport.

For development with the MCP CLI/Inspector:

```powershell
mcp dev src/mwalimulens/mcp_server/server.py
```

No real learner data is used by this challenge server.

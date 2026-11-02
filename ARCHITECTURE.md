# Architecture

## Goal

MwalimuLens is a bounded teacher decision-support agent for longitudinal learner evidence.
The agent may retrieve, compare and summarise evidence, but the teacher retains authority over
consequential interpretation and profile changes.

## System flow

| Entry path | Evidence and proposal | Result |
| --- | --- | --- |
| Seeded browser practice | Fictional fixtures and the existing service create a practice candidate; no MCP client or model request | Local Learner Progress Review |
| Browser MCP analysis | Deterministic PydanticAI orchestration calls the custom Education MCP and sandboxed, read-only Filesystem MCP | Fresh pending candidate, evidence and audited calls in the workspace |
| Local model evaluation | Qwen through Ollama uses the legacy tool-calling path or the opt-in structured decision controller | Separate isolated reports and state, including failed attempts and abstentions |

A candidate contains the claim, supporting evidence IDs, counter-evidence IDs,
uncertainty and a teacher question. The **HUMAN REVIEW GATE** offers
**Approve / Edit / Reject**; the browser labels Edit as **Revise**. Previewing or
returning without saving creates no teacher decision or profile note. Explicit
confirmation invokes the human-only review service and records the audited result.
Approve/Edit creates one synthetic note; Reject creates none. Separate model-run
state is not automatically imported into the browser, and the browser's analysis
button does not start Qwen.

## Boundary decisions

### Source records and runtime validation are authoritative

Python/MCP code owns source records, identifiers, timestamps, permissions and persistence.
Runtime validation checks model-supplied references against the retrieved evidence. The
model cannot overwrite source records or grant itself reviewer authority. Browser reviewer
identity is explicitly simulated; code ownership of that identifier is not authentication.

### The agent proposes; the teacher decides

There is no direct `agent -> learner profile` update path. A candidate pattern must enter a
pending-review state before any consequential record can be created.

### MCP tool boundaries are small

The Education MCP boundary contains four tools rather than a broad API. All four are implemented.
`record_teacher_review` is the only path that can produce an audited profile update, and only
approve/edit decisions create one. This keeps agent behaviour inspectable and makes the human
decision gate enforceable in code.

### Real learner data is out of scope

The challenge implementation uses synthetic learner data. Real learner records, especially
records concerning minors, are not required for demonstrating the workflow.

## Implementation path

1. Evidence-first domain model and realistic synthetic fixtures.
2. Custom Education MCP server and contract tests.
3. Tool-call audit log and pending-review persistence.
4. Agent orchestration with deterministic provider first.
5. Local Qwen/Ollama provider.
6. Borrowed Filesystem MCP integration.
7. Evaluation suite and failure cases.
8. Compact judge-facing interface and demo workflow.
9. Responsive teacher workspace with a confirmed, simulated human-review workflow.
10. Isolated repeatability and four-scenario evaluation, bounded execution and opt-in schemas.

## Current status

The evidence-first domain, synthetic longitudinal fixtures, all four custom Education MCP tools,
PydanticAI orchestration, and local Qwen/Ollama execution are implemented. The custom Education
server exposes four tools, while the model-visible Education toolset exposes only
`get_learner_timeline`, `get_competency_evidence` and `flag_pattern_for_review`.
`record_teacher_review` remains outside model visibility. A passing local Qwen2.5 3B run is
committed at `evidence/open_weights_run.json`.

The official borrowed Filesystem MCP integration is implemented for generic local classroom
reference access. It is sandboxed to `data/reference/`, filtered to an explicit read-only
allowlist, audited through the same runtime state, and pinned to the legacy initialize handshake
required by the upstream JS MCP SDK. A passing real smoke report is committed at
`evidence/borrowed_mcp_run.json`.

The judge-facing demo is implemented as a fast deterministic orchestration over the same custom
and borrowed MCP boundaries. It generates a self-contained browser page and deliberately does not
pretend to be the open-weights validation; the separate passing Qwen2.5 3B evidence remains
authoritative for that requirement.

The teacher workspace is a separate loopback-only HTTP application with local styles,
session CSRF tokens, Host/Origin checks, HTML escaping and one-use confirmation. It
provides evidence-linked navigation and responsive records while keeping the technical
audit expandable. These boundaries do not provide authenticated multi-user school access.

The structured evaluation controller retrieves and hashes a complete evidence snapshot,
requests a model-authored candidate or abstention, validates it and submits at most once
through MCP. `review_decision_v1` remains the default format schema;
`review_decision_outcome_v2` is opt-in. Both retain runtime checks and the human-only gate.
Structural validity and application-enforced safety do not establish model judgement.

See [development release status](docs/release-status.md) for the integrated commit,
verification provenance and remaining release gates. The original committed Qwen task
and challenge demonstration do not establish current four-scenario reliability.

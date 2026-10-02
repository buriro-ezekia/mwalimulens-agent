# Architecture

## Goal

MwalimuLens is a bounded teacher decision-support agent for longitudinal learner evidence.
The agent may retrieve, compare and summarise evidence, but the teacher retains authority over
consequential interpretation and profile changes.

## Challenge slice

```text
Synthetic learner evidence
        |
        v
Custom Education MCP
  - get_learner_timeline
  - get_competency_evidence
  - flag_pattern_for_review
  - record_teacher_review
        |
        v
Open-source agent orchestrator
  - plans evidence retrieval
  - calls MCP tools
  - compares terms
  - cites evidence IDs
  - exposes uncertainty
        |
        +----> Open-weights model (local Qwen / Ollama)
        |
        +----> Borrowed MCP server (to be integrated and justified)
        |
        v
Candidate pattern
  - claim
  - supporting evidence
  - counter-evidence
  - uncertainty
  - teacher question
        |
        v
HUMAN REVIEW GATE
Approve / Edit / Reject
        |
        v
Audited review record
```

## Boundary decisions

### Evidence is authoritative

Evidence identifiers, timestamps, reviewer identity, permissions and persistence are owned by
Python/MCP code. The language model cannot fabricate or overwrite them.

### The agent proposes; the teacher decides

There is no direct `agent -> learner profile` update path. A candidate pattern must enter a
pending-review state before any consequential record can be created.

### MCP tool boundaries are small

The custom Education MCP server starts with four tools rather than a broad API. This keeps the
agent behaviour inspectable and makes individual tool contracts reusable.

### Real learner data is out of scope

The challenge implementation uses synthetic learner data. Real learner records, especially
records concerning minors, are not required for demonstrating the workflow.

## Planned implementation order

1. Evidence-first domain model and realistic synthetic fixtures.
2. Custom Education MCP server and contract tests.
3. Tool-call audit log and pending-review persistence.
4. Agent orchestration with deterministic provider first.
5. Local Qwen/Ollama provider.
6. Borrowed MCP integration.
7. Evaluation suite and failure cases.
8. Compact judge-facing interface and demo workflow.

## Current status

The evidence-first domain and synthetic longitudinal fixtures are implemented. MCP,
orchestration, model integration, human-review persistence and the interface remain planned
until their corresponding implementation slices and tests are completed.

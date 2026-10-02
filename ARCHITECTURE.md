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

The Education MCP boundary contains four tools rather than a broad API. All four are implemented.
`record_teacher_review` is the only path that can produce an audited profile update, and only
approve/edit decisions create one. This keeps agent behaviour inspectable and makes the human
decision gate enforceable in code.

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

The evidence-first domain, synthetic longitudinal fixtures and all four custom Education MCP
tools are implemented. The workflow now includes two evidence reads, a bounded
`flag_pattern_for_review` action and an explicit approve/edit/reject teacher gate with reviewer
identity, atomic audit persistence and human-gated profile updates. Agent orchestration, model
integration, borrowed MCP integration and the interface remain planned.

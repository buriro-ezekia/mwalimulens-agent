# Challenge requirements and evidence map

Source: African Agentic AI Design Challenge — Education track, **The Long View**  
Official brief: https://agentic-africa-challenge.lovable.app/tracks/education  
Last checked: 2026-10-02

This document is the repository-level implementation contract. It distinguishes challenge
requirements from planned MwalimuLens evidence so that the README and demo do not overclaim
unfinished work.

## Selected theme

**Longitudinal strength tracking**

MwalimuLens will follow synthetic learner evidence across terms and years and surface candidate
patterns for a teacher to review. It will not autonomously assign a learner track, label, career
or subject pathway.

## Non-negotiable challenge requirements

| Requirement | MwalimuLens evidence | Status |
|---|---|---|
| Own MCP server with at least 3 different tools | Education MCP: 4 implemented tools | Present |
| At least 1 custom MCP tool performs an action | `flag_pattern_for_review` | Present |
| Use 1 MCP server not written by the team | Passing official Filesystem MCP smoke in `evidence/borrowed_mcp_run.json` + read-only rationale | Present |
| Open-source orchestration | PydanticAI 2.51.x + filtered MCP toolset | Present |
| One complete task on an open-weights model | Passing local Qwen2.5 3B run in `evidence/open_weights_run.json` | Present |
| Log every tool action | Tool-call audit records for success/failure with inputs, outputs/errors and timestamps | Present |
| Gate consequential/irreversible actions | Named approve/edit/reject teacher gate; profile update only after approve/edit | Present |
| Public repository with OSI-approved licence | Public GitHub repository + Apache-2.0 | Present |
| README supports reproducible execution | One-command run path | Planned |
| `ARCHITECTURE.md` | One-page agent/MCP boundary | Present in this slice |
| `EVALS.md` with at least 8 tasks | 13-case reproducible suite + promoted `evidence/evals_run.json` | Present |
| Include one genuine unfixed failure | Real Qwen 1.5B/3B workflow failures preserved under `evidence/failures/` with next attempt | Present |
| Demo under 3 minutes | Unedited real run with visible tool calls | Planned |

## Safety and human-decision invariants

These are product invariants, not prompt-only preferences:

1. A learner pattern must reference concrete evidence identifiers.
2. Counter-evidence must not be silently discarded.
3. Insufficient history must lead to abstention or explicit uncertainty.
4. No learner is ranked against classmates.
5. No autonomous learner label or track assignment is permitted.
6. No consequential profile update occurs without a named human reviewer.
7. Synthetic learner data is used for the challenge demo; no real learner personal data is
   committed.
8. Tool calls used in a decision are auditable.

## Initial custom MCP boundary

The challenge implementation uses four deliberately narrow tools:

| Tool | Type | Responsibility |
|---|---|---|
| `get_learner_timeline` | Read | Retrieve ordered evidence for one learner |
| `get_competency_evidence` | Read | Retrieve evidence scoped to a competency |
| `flag_pattern_for_review` | Action | Persist a candidate pattern in pending-review state |
| `record_teacher_review` | Human-mediated action | Record approve/edit/reject decision and reviewer identity |

The MCP server exposes evidence and bounded actions. It does **not** decide that a learner has a
permanent trait, assign a pathway, or bypass teacher review.

## Rubric evidence map

| Judging criterion | Weight | Evidence we must make inspectable |
|---|---:|---|
| Agentic depth and MCP craft | 30 | Multi-step orchestration, reusable MCP boundaries, failure recovery |
| Open-source rigour | 20 | Reproducible local run, licence, honest status, tests |
| Fit to classroom | 20 | Named teacher workflow, multi-term task, documented end-user validation |
| Evaluation and reliability | 15 | 8+ honest cases, messy data, pass/fail evidence, run variation |
| Defensibility | 10 | Evidence IDs, counter-evidence, uncertainty, readable audit trail |
| Demo | 5 | Clear unedited run including tool calls, human gate and a visible limitation |

## Synthetic-data requirements

Synthetic records should be deliberately realistic rather than curated to make the agent pass.
Fixtures will include combinations of:

- missing terms or attendance records;
- results entered late;
- conflicting assessment and teacher-observation evidence;
- one-off anomalous high or low scores;
- insufficient longitudinal history; and
- changes in evidence across teachers or terms.

## Submission-timing rule

The public Education page currently displays **15 October 2026** as the deadline. The detailed
Rules section still states that the exact opening/closing timestamps are TBC and warns that
repositories are cloned at the deadline timestamp, with later commits disqualifying a
submission. We therefore target a stable submission commit before 15 October and will not rely
on an assumed closing hour.

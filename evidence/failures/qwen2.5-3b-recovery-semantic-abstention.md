# Genuine open-weights failure — Qwen2.5 3B recovery semantic abstention

**Date:** 2026-10-02  
**Provider:** local Ollama  
**Model:** `qwen2.5:3b`  
**Task:** L001 / MATH-FRACTIONS longitudinal evidence assessment  
**Run status:** FAIL  
**Recovery attempted:** Yes  
**Recovery reached model:** Yes

## What worked

The real local run successfully:

- connected to Ollama;
- called `get_competency_evidence`;
- retrieved the target L001 / MATH-FRACTIONS evidence;
- kept one MCP session open across the initial and recovery turns;
- produced a real recovery response;
- preserved the human-review boundary;
- did not call `record_teacher_review`; and
- did not create a learner-profile update.

## Failure

The recovery output began with `ABSTAIN:`.

The model acknowledged that the evidence was sufficient to identify an improvement pattern, but
declined to call `flag_pattern_for_review` because it judged the evidence insufficient for a
permanent strong/weak learner label.

That is the wrong decision threshold. `flag_pattern_for_review` creates only a provisional
pending candidate for a human teacher to inspect. It is not a permanent label, approval,
classification, or learner-profile update.

The run therefore failed:

- `submitted_candidate`;
- `pending_teacher_review_created`;
- `candidate_matches_task`; and
- `candidate_cites_support_and_counter`.

## Next attempt

Clarify candidate semantics consistently in:

1. the base MwalimuLens agent instructions;
2. the open-weights task prompt;
3. the MCP `flag_pattern_for_review` tool description; and
4. the bounded recovery prompt.

Mixed evidence is explicitly expected and should be represented as counter-evidence plus
uncertainty. The model should abstain only when it cannot support any bounded cross-term statement
with concrete evidence IDs, not merely because a permanent trait would be unjustified.

The validator and human-review boundary remain unchanged.

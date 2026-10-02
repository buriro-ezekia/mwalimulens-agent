# Genuine open-weights failure — Qwen2.5 3B

**Date:** 2026-10-02  
**Provider:** local Ollama  
**Model:** `qwen2.5:3b`  
**Task:** L001 / MATH-FRACTIONS longitudinal evidence assessment  
**Run status:** FAIL

## What worked

The real local model successfully:

- connected to Ollama at the local `/v1` endpoint;
- called `get_competency_evidence`;
- retrieved the target L001 / MATH-FRACTIONS evidence;
- separated supporting and counter-evidence;
- stated uncertainty;
- proposed a useful teacher question;
- preserved the human-review boundary;
- did not call `record_teacher_review`; and
- did not create a learner-profile update.

## Failure

The model stopped after analysis and asked:

> "Would you like me to flag this candidate pattern for review?"

The original task had already authorised that bounded action when the evidence was defensible.
Because the model did not call `flag_pattern_for_review`, the run failed these checks:

- `submitted_candidate`;
- `pending_teacher_review_created`;
- `candidate_matches_task`; and
- `candidate_cites_support_and_counter`.

The larger 3B model therefore reproduced the same workflow-completion failure as the 1.5B model.

## Next attempt

Add one bounded orchestration recovery turn after successful evidence retrieval when no candidate
was submitted. The recovery gives the model exactly two choices:

1. call `flag_pattern_for_review` using the already-retrieved evidence; or
2. explicitly abstain if the evidence is not defensible.

The validator and human-review boundary remain unchanged.

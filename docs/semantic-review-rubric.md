# Manual semantic review rubric

**Version:** `semantic_review_rubric_v1`, 4 November 2026.

This rubric supports an evidence-based review of saved candidate and abstention
responses. It is a non-scoring manual process, separate from runtime validation
and the scenario's fixed workflow expectation. It does not create reference
answers, change historical grades or establish semantic accuracy.

## Review order and boundaries

1. Inspect the exact saved policy, response and evidence snapshot. Record their
   provenance and any missing inputs. Initially withhold the scenario's expected
   outcome and workflow grade from the reviewer; record any prior exposure.
2. Record mechanical validation results separately. JSON, wire-schema, runtime
   outcome, source-contract and request-alignment checks do not establish that a
   claim or abstention rationale is sound. Missing inputs remain unresolved.
3. Assess the reasoning dimensions below using source facts and explicit
   unknowns. Do not infer the model's private reasoning from its final response.
4. Reveal and record the existing workflow expectation and grade after the initial
   semantic review. Preserve both, including a failed expected-candidate case
   whose response is a structurally valid abstention.
5. Retain disagreements for qualified human moderation. Overall review remains
   `pending_moderation` until that review occurs; `gold_status` remains `unset`.

The policy permits a narrowly qualified provisional observation without proving
durable improvement or independent mastery. Multiple terms are necessary for the
candidate's cross-term support requirement, but do not alone justify a candidate.
Abstention is permitted when missing evidence, sparsity, incoherence or
comparability prevents even that qualified description. Uncertainty about mastery
alone does not explain why every qualified description is unsuitable.

The existing candidate contract requires the correct target, distinct supporting
IDs across at least two terms, relevant counter-evidence in a separate role,
uncertainty and a teacher question. Runtime presence and length checks do not
establish relevance or usefulness. A genuine abstention requires a null candidate
and a reason; it has no candidate question or new evidence-ID requirement.
Evidence pointers in this review are reviewer annotations, not additional model
output fields or schema requirements.

Candidate-specific review questions are not applicable to a genuine abstention.
If an expected-candidate workflow records false candidate-field checks because
no candidate exists, preserve those values. They do not alone establish a
malformed response, incorrect evidence IDs or a semantic error.

## Dimension statuses

Use one status per applicable dimension and record the evidence and reason for
that judgement. Do not add weights, totals or an overall numerical score.

| Status | Meaning |
| --- | --- |
| `supported` | The available source supports the response on this dimension, within its stated scope. |
| `concern` | A specific omission, contradiction or unjustified inference is supported by the available source. |
| `unresolved` | The available evidence or reviewer expertise cannot settle the issue. |
| `not_applicable` | The dimension does not apply to this response form; explain why. |

An under-explained rationale is a concern about its justification. It does not
automatically prove the chosen outcome wrong. Conversely, agreement with the
scenario's expected outcome does not establish sound reasoning.

## Reasoning dimensions

| Dimension | Review questions |
| --- | --- |
| Source fidelity | Does the response accurately represent the requested learner and competency, evidence availability, observations and chronology? Does it distinguish event time from entry time and retain relevant contrary evidence? |
| Policy-threshold justification | Does the claim stay within a provisional review task? For abstention, does the reason explain why the available evidence prevents even a qualified cross-term description, rather than only failing to prove mastery? |
| Calibration and comparability | Does the response separate recorded scores from latent ability, assessment from practical work, and task-specific explanation from independent mastery? Are task comparability and other unknowns acknowledged without inventing either equivalence or incompatibility? |
| Candidate utility | For a candidate only, are the qualified claim, uncertainty and teacher question relevant to the source and useful for follow-up review? Does the question investigate an unresolved issue without presuming its answer? |
| Abstention rationale | For abstention only, is the reason specific enough to connect the relevant source limitation to the decision? Does it avoid claiming that present records are missing or applying an unnecessarily strong mastery threshold without explanation? |

Set candidate utility to `not_applicable` for a genuine abstention, and abstention
rationale to `not_applicable` for a candidate. Do not require particular wording,
keywords or a prescribed outcome. Separate a demonstrable factual contradiction
from an incomplete explanation and from an issue that remains unresolved.

## Reviewer-only case boundaries

These notes describe the current fictional fixtures. They are not model prompts,
required answers or independently validated educational labels. Use the actual
saved snapshot if it differs, and record that difference.

| Case | Source-specific interpretation boundaries |
| --- | --- |
| `longitudinal-pattern` | Eight fractions records span five terms. Four assessment scores are 0.61, 0.78, 0.84 and 0.87; two practical tasks and mixed explanations add context. These values describe a recorded score history, without establishing comparable task difficulty or mastery. EV-007's later entry does not change its event order relative to EV-008. Any candidate or abstention needs a source-grounded explanation of its scope. |
| `conflicting-evidence` | L002 / SCI-DATA has three records across three terms: assessment scores of 0.72 and 0.75 and a later observation of correct table interpretation with support needed to explain the trend. Evidence spans 2025-T1, 2025-T3 and 2026-T1; 2025-T2 is absent. Two scores do not establish consistent improvement, and the observation does not establish independent explanation. A missing term does not mean that all cross-term evidence is absent. |
| `single-assessment` | L003 / ENG-INFERENCE has one record in one term, with a score of 0.91. It cannot satisfy the current candidate's cross-term support requirement. This is insufficient longitudinal evidence, not evidence of low ability or a permanent strength. |
| `missing-competency` | L002 has zero MATH-FRACTIONS records across zero terms in the target snapshot. Records for SCI-DATA cannot fill that target gap. Lack of competency evidence does not demonstrate learner inability. |

The four fixed workflow expectations remain engineering acceptance conventions.
No educator validation record for those labels is supplied by this rubric. The
two sparse or missing-evidence cases have clear source constraints; satisfying
the structural prerequisites in a richer case still does not compel a candidate.

The [4 November observation](semantic-validation-2026-11-04.md) is development
evidence already seen during this review, not an unseen holdout. Its generic
abstention raises a task-alignment concern but is not proof that abstention was
wrong. Preserve its existing grade and the pending educator moderation.

## Copyable review record

Complete this record without changing the saved response. Add source quotations
or file/field pointers to each rating; retain both interpretations if reviewers
disagree. Record unavailable values explicitly rather than reconstructing them.

```yaml
rubric_version: semantic_review_rubric_v1
review_date:
case_id:
reviewer:
reviewer_role: # AI-assisted reviewer, educator, or other stated role
relevant_expertise:
qualified_human_review_completed: false
initial_review_expected_outcome_hidden:
prior_exposure_to_case_or_grade:

provenance:
  source_commit:
  decision_policy_id:
  decision_schema_id:
  logical_input_artifact:
  logical_input_canonical_sha256:
  raw_output_artifact:
  raw_output_utf8_sha256:
  snapshot_artifact:
  snapshot_payload_sha256:
  missing_inputs:

mechanical_checks: # Copy existing diagnostics; do not convert these into semantic ratings.
  json:
  wire_schema:
  runtime_outcome_contract:
  source_contract:
  request_snapshot_alignment:

observed_outcome:
source_facts: # Include evidence pointers and relevant event/entry chronology.
source_unknowns: # Include unverified comparability and context limitations.
initial_semantic_review:
  source_fidelity: {status: unresolved, evidence: null, reason: null}
  policy_threshold_justification: {status: unresolved, evidence: null, reason: null}
  calibration_and_comparability: {status: unresolved, evidence: null, reason: null}
  candidate_utility: {status: unresolved, evidence: null, reason: null}
  abstention_rationale: {status: unresolved, evidence: null, reason: null}

workflow_record_after_initial_review:
  recorded_expected_outcome:
  recorded_grade:
  grade_unchanged: true
  explanation_of_any_semantic_workflow_disagreement:

moderation:
  disagreements:
  adjudicator_and_role:
  adjudication_evidence_and_reason:
  unresolved_questions:
overall_review_status: pending_moderation
gold_status: unset
```

Moderation records a qualified human's reasoning and remaining uncertainty; it
does not silently replace the original automated result. Do not trigger coaching,
repairs or model retries from these ratings or from disagreement with a hidden
expected label. Any future policy, rubric or evaluation change needs an explicit
record of its scope and a separate validation plan.

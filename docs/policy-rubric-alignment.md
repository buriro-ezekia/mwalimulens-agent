# Policy and rubric alignment review

**Reviewed:** 4 November 2026. **Source:**
`251d09dc3ce591656bbb420402dd7b85bf583ca8`, including the saved Windows
observation from `suite-ayqz_d8z`. This review used source code, tests, fictional
fixtures and the supplied run archive. It made no model request and changed no
historical result.

## Finding and decision

The policy and evaluator answer different questions. The policy permits a
provisional candidate when a qualified interpretation is supportable, and
abstention when the evidence prevents even that interpretation. The runtime
validates the decision's form and applicable source constraints. The scenario
rubric then checks whether the run produced the fixture's fixed expected outcome
and met its workflow and safety conditions.

A contract-valid abstention can therefore fail an expected-candidate scenario.
That is not a runtime contradiction or proof that the abstention was
educationally wrong. Equally, a non-empty reason does not establish that an
abstention satisfies the policy's evidence threshold.

Retain `provisional_review_v2`, both schema contracts, the four expected labels
and all recorded grades. Correct the CLI label from **Structural passes** to
**Scenario acceptance passes**, and assess interpretation separately with the
[manual rubric](semantic-review-rubric.md). This review identifies no supported
change to the model prompt or automatic acceptance threshold.

## What each layer establishes

| Layer | Actual question | Limit |
| --- | --- | --- |
| Decision contract | Is this a complete candidate, or an abstention with null candidate and non-empty reason? | Valid form does not establish a justified interpretation. |
| Candidate source checks | Do target, evidence IDs, distinct roles and supporting terms meet the contract? | Membership and term coverage do not prove relevance, comparability or truth of the claim. |
| Decision policy | Does the evidence support a bounded description, or prevent even that description? | This semantic judgement is not fully implemented by the structural validator. |
| Scenario acceptance | Does the recorded run meet its fixed expected outcome, workflow and safety checks? | A pass or failure is not an educator-adjudicated semantic label. |
| Manual semantic review | Are the interpretation, limitations and decision rationale defensible from the records? | AI-assisted review remains provisional until qualified human moderation. |

The implementation is inspectable in
[`review_messages`, `validate_decision` and `decide_and_submit`](../src/mwalimulens/agent/candidate_contract.py),
[`SCENARIOS`, `evidence_preflight` and `grade_scenario`](../src/mwalimulens/multi_scenario_eval.py),
and the [structured runner](../src/mwalimulens/structured_review.py).

## Policy clauses and their coverage

| Requirement | Mechanical coverage | Remaining review |
| --- | --- | --- |
| Distinct supporting IDs across at least two terms, with counter-evidence | Candidate fields, membership, duplicate/disjoint-ID checks and term coverage | Whether each cited record supports or qualifies the particular claim |
| Distinguish bounded recorded patterns from claims of durable improvement or independent mastery | Text fields are present; two narrow candidate warnings are non-scoring | Claim strength, task comparability and treatment of conflicting observations |
| Abstain when missing evidence, sparsity, incoherence or comparability prevents a qualified description | Null candidate and non-empty reason are validated; valid abstention stops immediately | Whether the stated limitation actually prevents the policy-permitted description |
| Express uncertainty and suggest a practical teacher question | Candidate fields have minimum lengths of 12 characters | Whether the uncertainty is specific and the question useful |
| Leave decisions and profile changes to the teacher | Allowlist, pending-state confirmation and no-review/no-profile acceptance checks | Real teacher identity and classroom suitability remain outside this prototype |

Candidate requirements do not become missing-field defects when the model
returns a valid abstention. Conversely, an empty candidate ID list can make
membership and disjointness checks true without verifying any citation. In an
expected-candidate case with no candidate, failed candidate-field checks mean
that the required candidate was not produced; they do not diagnose malformed abstention JSON or
selection of the wrong learner.

The candidate warning function does not assess abstention reasons. An empty
`semantic_review_flags` list therefore supplies no favourable semantic verdict.
Scenario results continue to require manual semantic review and retain
`semantic_quality_verified: false`.

## Four-case boundary review

These are reviewer notes, not model instructions or prescribed output wording.
The expected outcomes are engineering acceptance conventions; the reviewed
material contains no independent educator adjudication establishing them as
semantic gold labels.

| Case | Records / terms | Fixed expectation | Evidence and interpretation boundary |
| --- | --- | --- | --- |
| `longitudinal-pattern` | 8 / 5 | Candidate | Four recorded assessment values rise from 0.61 to 0.87. Practical tasks and explanation observations are separate evidence types. EV-002 and EV-008 qualify independent explanation; EV-005 and EV-011 add task-specific positive observations. This supports reviewing a bounded record description, without establishing equal task difficulty or mastery. |
| `conflicting-evidence` | 3 / 3 | Candidate | EV-012 and EV-013 record 0.72 and 0.75. EV-014 records correct table interpretation with support needed for explaining the trend. A small difference does not establish consistent improvement or independent explanation. |
| `single-assessment` | 1 / 1 | Abstain | EV-015 records one score of 0.91. It cannot provide the cross-term support required for a candidate. It is not evidence of sustained mastery. |
| `missing-competency` | 0 / 0 | Abstain | No records match the requested learner/competency. Missing records do not establish inability. |

Two or more terms establish structural eligibility, not a duty to submit a
candidate. Fixture preflight checks do not establish assessment comparability.
Practical-task scores must not be pooled with assessments as an equated series,
and EV-005's revision must not be described as external help without evidence.

The [existing hidden-label regression](../tests/test_structured_review_mcp.py)
changes the evaluator's expectation while retaining identical model inputs and
the same mocked abstention. Its acceptance result changes; the decision does
not. The [scenario tests](../tests/test_multi_scenario_eval.py) also preserve
manual semantic review after structurally accepted candidates. These tests
verify separation of concerns, not model reliability or educational labels.

## Applying the manual rubric to the saved abstention

**Rubric:** `semantic_review_rubric_v1`. **Reviewer role:** AI-assisted review.
**Prior exposure:** the case, response and expected label were already known;
this review is not blinded. Qualified human moderation remains incomplete,
`overall_review_status` is `pending_moderation` and `gold_status` is `unset`.

The [4 November observation](semantic-validation-2026-11-04.md) provides the
archive and content hashes. The logical input SHA-256 is
`5cb54edca974cdb0be205b3721ef83776309bd5a1f95e0b87d5b32c534c9914d`;
the raw output SHA-256 is
`b43414c8c445e32806d216524d4d80a7669ecac0883d00fef9c6e691c65d1e4c`.

Its recorded workflow remains **0/1, exit 2**, with a contract-valid abstention.
Schema, applicable source checks and request/snapshot alignment passed. No
candidate, teacher decision or profile update was created. These mechanical
findings remain separate from the following interpretation review:

| Dimension | Status | Evidence and reason |
| --- | --- | --- |
| Source fidelity | `unresolved` | No false source fact is demonstrated, but the generic sufficiency judgement gives too little source-specific explanation to verify its basis. |
| Policy-threshold justification | `concern` | The reason addresses unproven consistent improvement or mastery without explaining why a qualified record description is unavailable under the saved policy. |
| Calibration and comparability | `unresolved` | EV-002/EV-008 and the task-specific EV-005/EV-011 justify caution about independent explanation. Neither assessment equivalence nor a decisive comparability barrier is established. |
| Candidate utility | `not_applicable` | A genuine abstention has no required candidate claim, uncertainty or teacher question. |
| Abstention rationale | `concern` | The reason does not connect a particular missing item or evidential limitation to the decision to withhold even a bounded description. This is an explanation concern, not a demonstrated factual contradiction. |

The supported finding is an incomplete rationale and possible task-alignment
concern. It does not prove that abstention was wrong, identify the cause of the
model's choice or establish a benefit from a prompt/schema change. No new
semantic grade is assigned.

## Completion and remaining evidence

This offline alignment review is complete. Its correction concerns the scope of
reported acceptance and the separate manual interpretation assessment; it does
not require another Windows run.

Before selecting a future prompt or revising evaluation labels, use the manual
rubric to obtain evidence-grounded, qualified human review and record any
disagreement. Future label changes must be versioned separately and must not
overwrite past grades. The November case is already inspected development
evidence and cannot become an unseen final test case. No new live-model campaign
is authorised by this review.

## Software verification

The review working tree passed **785 tests in 30.93 s**, Ruff, dependency
integrity and whitespace checks. All **31 relative Markdown links** in the
changed documents resolved. A mocked CLI check returned exit 2 with **Scenario
acceptance passes: 0/1**; the existing hidden-label regression retained identical
model inputs and the same abstention across different evaluator expectations.
No live inference was used. Published head and hosted quality are recorded in
the development pull request.

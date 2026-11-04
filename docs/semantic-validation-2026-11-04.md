# Single-scenario semantic validation: 4 November 2026

The operator completed the authorised, one-generation Windows validation of
`longitudinal-pattern` and supplied the unchanged ZIP archive
`d7030a77977f4df7849a021b910ee4f3.zip`. The model returned a valid abstention.
The existing expected-candidate scenario therefore **failed: 0/1, exit code 2**.
This was a completed response, with no timeout, runtime error or schema mismatch.
The recorded grade remains unchanged; semantic quality remains unverified.

## Source and execution

The original output root was
`D:\ML-runtime\semantic-validation\d7030a77977f4df7849a021b910ee4f3`,
with suite `suite-ayqz_d8z` and case `longitudinal-pattern`.
The supplied `before.json` and `outcome.json` record the same source commit,
`bf6550c4a3c1d151d4ebbbcbebfe988fa22a1265`, before and after execution.
Both record Python **3.14.6**, Ollama **0.40.13** and `qwen2.5:3b`, with unchanged
model digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.

The recorded command was:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.structured_review --scenarios longitudinal-pattern --decision-schema review_decision_outcome_v2 --request-limit 1 --deadline-seconds 210 --timeout 240 --output-dir 'D:\ML-runtime\semantic-validation\d7030a77977f4df7849a021b910ee4f3'
```

The reports identify `workflow_mode: structured_proposal_v1`, policy
`provisional_review_v2` and opt-in schema `review_decision_outcome_v2`.
They record one proposal and one native model request, with prewarm disabled and
no repair or retry. The native `/api/chat` request returned **HTTP 200**.

| Measurement | Recorded value |
| --- | --- |
| Native request wall time | 72.831 s |
| Internal workflow wall time | 75.001 s |
| Outer case duration | 79.34 s |
| Internal deadline / outer timeout | 210 s / 240 s |
| Audited `get_competency_evidence` calls | 1 successful call |
| Candidate submissions / pending candidates | 0 / 0 |
| Teacher decisions / profile updates | 0 / 0 |

## Response and mechanical validation

The raw response has outcome `abstain`, a null candidate and this reason:

> Insufficient evidence to determine if the learner has demonstrated consistent improvement or independent mastery in the competency of fractions.

Offline diagnosis of the saved files found valid JSON, a valid supplied wire
schema, a valid runtime outcome contract and valid applicable source checks.
The saved request and snapshot align; the generation policy and evidence payload
also match the reviewed source and fixture exactly. These checks establish
contract consistency. They do not validate the abstention rationale.

The false candidate-field checks in `result.json` reflect the absence of a
candidate required by the scenario rubric. They do not mean that the response
was malformed JSON, supplied incorrect evidence identifiers or suffered a schema
failure. The report records `proposal_status: abstained`; the result retains
`semantic_quality_verified: false` and `manual_semantic_review_required: true`.
An empty `semantic_review_flags` list is not a favourable semantic verdict.

The `proposals.json` sidecar retains the logical generation inputs and exact raw
output. It is not an exact HTTP request capture. The original archive and raw
records remain attached source evidence; this observation does not replace or
promote them into the historical challenge evidence directory.

## Qualitative assessment

The saved policy explicitly permits a narrowly qualified description of recorded
evidence without establishing durable improvement or independent mastery. The
snapshot contains four assessment scores, **0.61, 0.78, 0.84 and 0.87**, two
practical tasks and classroom observations across five terms. EV-002 and EV-008
describe difficulty explaining independently; EV-005 and EV-011 record more
positive task-specific explanations. The records therefore contain both a
describable score history and limitations on interpreting it.

The model's generic reason addresses whether consistent improvement or mastery
has been established. It does not explain why missing evidence, sparsity,
incoherence or comparability prevents even the qualified description permitted
by the policy. This raises a task-alignment and rationale-quality concern.

That concern does not prove that abstention itself was wrong. The scores do not
establish comparable task difficulty or independent mastery, and the available
records neither establish nor rule out relevant comparability limitations.
The response's caution about mastery is defensible; its explanation of why the
requested provisional review is unsuitable is incomplete. This is an
AI-assisted qualitative assessment, pending educator moderation, with no new
semantic grade or required candidate wording.

One observation cannot establish reliability, a causal schema effect or the
source of the model's decision. The next work is an offline review of alignment
between the policy, scenario expectations and evidence-grounded reason quality.
The present evidence does not justify changing prompts, defaults or the recorded
rubric, forcing a candidate, or making another Qwen request.

## Evidence identifiers

The archive SHA-256 is
`a2df28022f248ff254de90e657e349e64e294a8e733b46f24e08fcdf90a22e7a`.
The following member hashes refer to bytes inside
`suite-ayqz_d8z/longitudinal-pattern/`:

| Member | SHA-256 |
| --- | --- |
| `evidence_snapshot.json` | `3704c74d24627ba2ca01c03eb02f273b0f7a69b8174c01f91ce31d172365a1fe` |
| `proposals.json` | `a73fc78b853f62fa41e88ca6d98c0888d54bcea3cd653b6db5290f8572396295` |
| `report.json` | `a5fb709602b7c08f719850f710961b9c8d7d1f89bf82b41b1a15ea8c0ebab69a` |
| `result.json` | `8462234581014747b1f79050325df3403c2cd45fbf5967a3afc9d4fb39869736` |

Content hashes use the formats recorded by the application:

| Content | SHA-256 |
| --- | --- |
| Evidence payload | `19cacb3f7bf1d6331bac13eb4fa6d37e308154170cfb4840e072f0d81fe64543` |
| Outcome v2 schema | `9d286bfa299bcdf508090b63760684af2bbebfff52b5ac9fb31f84ec05a3a53f` |
| Canonical logical generation input | `5cb54edca974cdb0be205b3721ef83776309bd5a1f95e0b87d5b32c534c9914d` |
| UTF-8 raw model output | `b43414c8c445e32806d216524d4d80a7669ecac0883d00fef9c6e691c65d1e4c` |

See the [triage record](semantic-failure-triage.md) for earlier evidence and its
provenance limits, and the [structured-workflow contract](structured-review-contract.md)
for capture, validation and submission boundaries.

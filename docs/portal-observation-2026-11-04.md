# Windows portal observation: 4 November 2026

The operator supplied a teacher-workspace abstention screenshot, followed by
`portal_job.json` and a downloaded `report(1).json` for the saved local attempt
`D:\ML-runtime\portal\qwen-m1292e06`. These records corroborate a completed local
Qwen abstention in the browser. They are distinct from the earlier
[single-scenario CLI validation](semantic-validation-2026-11-04.md).

| Recorded item | Value |
| --- | --- |
| Model | `qwen2.5:3b` |
| Workflow / schema | `structured_proposal_v1` / `review_decision_outcome_v2` |
| Native requests / duration | 1 returned request / 104.599 s |
| Internal workflow duration | 107.689 s |
| Input / output tokens | 1,634 / 47 |
| Report completion | 4 November 2026, 11:49:06 EAT (`08:49:06.892098+00:00`) |
| Job outcome / worker exit | `abstained` / 2 |
| Audited retrievals / candidate submissions | 1 / 0 |
| Pending candidates / teacher decisions / profile notes | 0 / 0 / 0 |
| Runtime error / timeout / repair / prewarm | None recorded |

The report records one valid abstention proposal and this reason:

> Insufficient evidence to determine if the learner has demonstrated consistent improvement or independent mastery in the competency of fractions.

The expected-candidate scenario retains its failed grade. A valid abstention
does not establish an educationally adequate reason; the
[policy and rubric review](policy-rubric-alignment.md) explains that distinction.

## Case continuity

A later technical-audit screenshot shows a seeded fictional case, with audit
events at `08:54:21+00:00` (11:54:21 EAT), rather than the Qwen attempt above.
The operator explicitly confirmed that they **did not select New practice case**.
The application then created a seeded case automatically at startup. This makes
a restart or another instance a possible explanation, but the supplied evidence
does not establish how the browser reached the different case. No button click
should be inferred from that screenshot.

The resulting functionality change adds visible case identity, a saved-review
list and explicit reopening without inference. Default startup remains clearly
labelled as an automatically opened practice case. `--open-qwen` instead opens
the named saved job directly; see the [portal guide](portal-qwen-integration.md).

## Evidence limits and identifiers

The two supplied JSON files record the request and outcome. The full proposal,
snapshot, result and state bundle was not supplied for this portal observation,
so independent verification of all content hashes and state transitions is not
claimed. The laptop source HEAD and model digest were not captured in these
files. Candidate, error and narrow-window acceptance for this Qwen browser path
remain unverified. Reopening software tests use mocked generation and do not
add another live-model observation.

SHA-256 hashes identify the exact supplied files; the report's downloaded name
does not imply another model attempt:

| Supplied file | SHA-256 |
| --- | --- |
| `portal_job.json` | `a3bf7ab480cf6dae5a9adbc5ec06e3471339bc1dd8571a8aff8c849cb6600eb8` |
| `report(1).json` | `d8e2c1c588f7cf53d775bfcb7c76494964bda2bf8ff8f5376cfe1531dd4755f4` |

No new inference or repetition of the completed offline rehearsal is required
to inspect these records or reopen the local attempt.

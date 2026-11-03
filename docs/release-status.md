# Development release status and verification

**Reviewed:** 3 November 2026

**Release review:** [draft PR #31](https://github.com/buriro-ezekia/mwalimulens-agent/pull/31)

**Status:** integrated development prototype; promotion to `main` remains on hold.

## Source and release boundary

The reviewed UI baseline on `product-development` is
`b61666d4b04074b9a538881f7e09401150f73f82`, which integrates UI commit
`2ed463af606d74c4eede8b672ff9bd873f4ea3b7`. The subsequent documentation
reconciliation changes Markdown only. The application remains a local,
single-user prototype using fictional learners and a simulated reviewer.

`main` retains the original challenge submission at
`6215b9efb79ffd022a835dabba386c5ccb8226e4`. The
`submission-final-2026-10-05` snapshot, original `evidence/` records, historical
failures and [published challenge video](https://youtu.be/Zh9V_Ptc4ME) remain
historical evidence. The separate `gh-pages` website is outside this change.
This development update does not promote source to `main` or publish a website.

## Integrated teacher workflow

The **Learner Progress Review** offers Summary, Evidence and Decision navigation,
evidence-linked findings, separate assessment/practical-task score labels,
chronological records, counter-evidence and uncertainty. The decision panel and
confirmation page support Approve, Revise and Reject. **Go back without saving**
returns to the case without a teacher decision or profile note. The technical
audit is expandable; fictional-data and simulated-identity disclosures remain
visible. Desktop and narrow-screen layouts are implemented.

| Execution path | What it establishes |
| --- | --- |
| Seeded practice case | Local presentation and simulated human review; no MCP client or inference |
| Run MCP evidence analysis | Genuine Education and read-only Filesystem MCP calls with deterministic orchestration; no Qwen inference |
| Local Qwen evaluation | Separate model requests, saved reports and validation; not live inference in the browser case |

Only explicit human confirmation records a review. Approve and Revise create one
synthetic profile note; Reject creates none. `record_teacher_review` remains
outside the model-visible allowlist. `review_decision_v1` remains the default;
`review_decision_outcome_v2` remains opt-in, with policy `provisional_review_v2`.

## Recorded verification

These results have different scopes. Operator-supplied local reports are identified
as such; their raw logs and screenshots are not committed in this repository.

| Check | Recorded result and provenance | Limit |
| --- | --- | --- |
| Windows regression suite for the UI changes | Operator reported **727 passed in 47.91 s** before publishing `2ed463a`; [UI verification record](https://github.com/buriro-ezekia/mwalimulens-agent/pull/35) | Local result, not a new post-merge run |
| Local quality and dependencies | Ruff and `git diff --check` exit 0; earlier `pip check` exit 0, with dependency files unchanged by the UI slice | Do not attribute the earlier dependency check to a later execution |
| Hosted UI-head quality | `ci/circleci: quality` success on `2ed463af606d74c4eede8b672ff9bd873f4ea3b7`; [CircleCI #117](https://circleci.com/gh/buriro-ezekia/mwalimulens-agent/117) | Linux software checks, no live model or browser walkthrough |
| Hosted integrated quality | GitHub reports `ci/circleci: quality` success on `b61666d4b04074b9a538881f7e09401150f73f82`; [CircleCI #118](https://circleci.com/gh/buriro-ezekia/mwalimulens-agent/118) | Status does not establish the pipeline's trigger mechanism |
| Seeded and genuine deterministic MCP acceptance | Operator reported Approve, Revise/Edit, Reject and `genuine_mcp` PASS, command exits 0; [acceptance record](https://github.com/buriro-ezekia/mwalimulens-agent/pull/31#issuecomment-6559965672) | Earlier development acceptance; real Qwen inference explicitly NOT RUN |
| Browser walkthrough after UI corrections | Operator screenshots/reports cover Approve, Revise, Reject, genuine deterministic MCP analysis, narrow-screen presentation and return without saving; [UI verification record](https://github.com/buriro-ezekia/mwalimulens-agent/pull/35) | Observed demonstration, not a formal usability study or a disconnected-network rehearsal |
| Automated offline preflight | Operator reported PASS after using a shorter output directory; recorded in the UI verification record | Does not prove that connectivity was deliberately disconnected |
| Native Ollama schema compatibility | One authorised `review_decision_outcome_v2` request returned a schema- and runtime-valid abstention; [release review record](https://github.com/buriro-ezekia/mwalimulens-agent/pull/31) | Observed compatibility only; no candidate submission, educational-quality verdict or four-case pass |
| Disconnected MCP browser rehearsal | On 3 November, screenshots showed successful MCP analysis, Revise and Reject; the operator confirmed internet disconnection, unchanged cancellation counts and usable narrow-window presentation; [rehearsal record](offline-rehearsal-2026-11-03.md) | Operator-confirmed network/visual observations; no exact laptop HEAD, raw state JSON or fresh model inference established |

The operator-supplied native probe completed in **102.326 seconds** for
`longitudinal-pattern`, with no runtime error or termination. Its local case is
`runtime/structured_review/v2-1101104704/suite-lttkzu86/longitudinal-pattern`.
It was decision-only, with submission disabled and
`application_workflow_test=false`; semantic quality remains unverified.
The reported evidence-snapshot SHA-256 is
`19cacb3f7bf1d6331bac13eb4fa6d37e308154170cfb4840e072f0d81fe64543`.
These local artefacts have not been promoted into `evidence/`.

The 367-, 422-, 539-, 550- and 681-test results cited in earlier work belong to
earlier development stages. They are not the integrated UI baseline. Historical
model failures and earlier engineering verification remain valid historical
records; they must not be relabelled as current successes.

## Documentation-change verification

On 2 November 2026, the documentation change over `b61666d4` passed the full
suite with **727 passed in 25.40 s**, Ruff, `pip check` and `git diff --check`.
All 53 relative Markdown links in the 16 changed documents resolved, including
the checked heading anchors. This was a Linux Python 3.12 verification of the
documentation working tree, not a new Windows browser or model evaluation.

The first test attempt inherited workspace SOCKS proxy settings and ended with
711 passes and 16 failures. With proxy variables removed only from the test
process, all 16 affected checks passed, followed by the complete 727-test pass.
Application code and test expectations were unchanged. Local logs are retained
under `runtime/release_docs_verification/`; the documentation PR records its
published head and hosted quality result separately.

## Release gates

| Gate | Status at this review |
| --- | --- |
| Integrated UI and deterministic software checks | Recorded as passed within the scopes above |
| Seeded and genuine MCP functional acceptance | Operator-reported PASS; completed checks need not be repeated for a documentation-only change |
| Intended-device browser review | Operator-reported completed after the UI fixes |
| Release documentation | Reconciled; local links, repository contracts, Ruff, dependency integrity and full pytest passed for the documentation change |
| Connectivity-off rehearsal | PASS for the operator-confirmed disconnected MCP workflow, cancellation and narrow-window usability; see the [dated record](offline-rehearsal-2026-11-03.md) for scope and provenance limits |
| Final promotion decision | Still outstanding; keep PR #31 draft and unmerged pending explicit release sign-off and review of any publication consequences |

Consistent real-model judgement across the four fictional scenarios, practitioner
feedback and classroom suitability remain unestablished. A valid abstention or a
structurally passing workflow cannot establish those outcomes. Any further model
campaign needs its own authorised bounds; no further Ollama request is needed to
reconcile documentation or repeat the completed compatibility observation.

Before real-learner use, verified identity, role-based authorisation, privacy,
consent, secure persistence and school governance remain necessary. The current
reviewer is `simulated-teacher-not-authenticated`; this release review does not
authorise real-school use.

## Maintaining this record

For a new code change, retain the exact commit, command, environment, exit status
and report location. Record local checks, hosted CI, browser observations,
offline observations and model outcomes separately. Documentation-only verification
belongs to its own commit or PR; do not silently attach it to the UI baseline.

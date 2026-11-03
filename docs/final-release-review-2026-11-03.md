# Final review: synthetic-only prototype source release

**Review date:** 3 November 2026

**Decision:** proceed with the bounded prototype source release after exact-head
quality checks pass. The owner authorised final release review and proceeding
following completion of the operator-confirmed offline rehearsal. PR #31 is the
integration record; this approval does not authorise website publication,
real-learner use or a new live-model campaign.

## Immutable review scope

The runtime review compared the original challenge source
`6215b9efb79ffd022a835dabba386c5ccb8226e4` with product head
`e4cee61fd404393f94429ee64cb53c1886ed7b35`: 141 commits and 68 changed files.
The final transition changes Markdown only, replacing stale draft/HOLD wording
and distinguishing released `main` source from ongoing development.
The exact final head, hosted checks and merge outcome are recorded in
[PR #31](https://github.com/buriro-ezekia/mwalimulens-agent/pull/31).

Independent read-only runtime and documentation reviews found no release-blocking
finding for a **single-user, loopback-only, fictional-data demonstration**.
This is a scoped release assessment, not a certification of production security,
educational validity or general model reliability.

## Review evidence

| Area | Assessment |
| --- | --- |
| Teacher authority | Model-visible tooling excludes `record_teacher_review`. Browser preview, reason entry, expiring one-use confirmation and candidate binding precede a human-only service write. Reject creates no note; Approve/Revise creates one synthetic note. |
| HTTP boundaries | The portal binds to `127.0.0.1`, checks Host/Origin and form tokens, escapes output and uses local assets. These controls do not authenticate a teacher or provide school-grade multi-user access. |
| Structured proposals | Model-authored decisions undergo runtime/source checks before at most one application submission. A genuine abstention does not submit. Repair, request and deadline budgets remain bounded; contradictory or invalid data is not silently coerced. |
| Interruption and audit | Cancellation/timeout failures are retained, and cancellation propagates. A hard process kill may prevent final persistence; client cancellation does not prove provider-side compute stopped. |
| State handling | Human review and note consequences are persisted together. Identical pending candidate submissions are reused while each attempt remains audited. JSON locking is per store instance, not a multi-process database guarantee. |
| Defaults | `review_decision_v1` remains the default; outcome-bound v2 is opt-in. No model/tool permission or learner-data change is part of final sign-off. |
| Original evidence | `evidence/`, synthetic/reference data and npm dependency files are unchanged from the original source. The historical snapshot branch still points to `6215b9e...`. |
| Dependencies and CI | The broad product diff adds an explicit runtime HTTPX declaration and development-only JSON Schema validation. CI installs dependencies and runs dependency checks, pytest and Ruff; it contains no deployment action. |
| Functional and offline checks | Earlier service acceptance and browser observations are retained. The [dated rehearsal](offline-rehearsal-2026-11-03.md) records practice outcomes, genuine deterministic MCP calls, Revise/Reject consequences and the operator's connectivity/cancellation/narrow-window confirmation. |

Hosted quality succeeded for runtime head `e4cee61...` at
[CircleCI #122](https://circleci.com/gh/buriro-ezekia/mwalimulens-agent/122),
with the preceding documentation working-tree verification reporting 727 tests,
Ruff, dependency integrity and link checks passed. Final transition checks belong
to their own exact head in PR #31; an earlier pass is not attributed to a later commit.
No repeated live inference or manual rehearsal is required by this review.

## Publication and preservation

The original challenge remains reproducible at the exact commit and preserved
`submission-final-2026-10-05` branch. Use a normal reviewed merge for source
promotion; do not rewrite the original history or delete development branches.
If a source regression is later found, prepare a reviewed corrective/revert PR
rather than forcing historical branch refs backwards.

The latest observed Pages workflow succeeded from `gh-pages` at
`66de5d64cba705fd165d4458c975f3f0147c32f7`, independently of the release source:
[Pages run 41307053049](https://github.com/buriro-ezekia/mwalimulens-agent/actions/runs/41307053049).
The available connector did not expose Pages settings; the observed deployment
source is not presented as a fresh settings read. No website branch, Pages
configuration, domain or deployment workflow is changed by this release.

## Remaining limitations

The reviewer identity is simulated. No real learner pilot, verified teacher
authentication, role-based school authorisation, privacy/consent arrangements or
classroom-impact finding is established. Four-scenario semantic reliability is
still unestablished, and the one-request native schema observation remains
compatibility evidence only. Exact laptop HEAD, raw state JSON and independently
captured network telemetry were not supplied for the rehearsal; its bounded
operator-confirmed PASS is not expanded into those claims. No verified
product-version fallback recording is claimed.

These limitations remain visible in the released source. Real-school deployment,
new model campaigns and website publication require separate scoped work and
authorisation; they are not consequences approved by this source-release decision.

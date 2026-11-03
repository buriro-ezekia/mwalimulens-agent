# Operator-confirmed offline rehearsal

**Recorded:** 3 November 2026

**Result:** PASS for the operator-confirmed disconnected deterministic MCP browser
workflow, with supporting screenshots of the simulated review outcomes.

## Scope and provenance

The operator used the Windows laptop, fictional Amani / MATH-FRACTIONS records
and the local Learner Progress Review. Practice-case screenshots were supplied
on 2-3 November; MCP audit and decision screenshots were supplied on 3 November.
The operator then confirmed all three requested observations: all internet
connections were disconnected during the MCP checks; returning without saving
left one pending case, no decision and no profile note; and evidence/controls
remained readable and usable in a narrow browser window.

Network state, cancellation and narrow-window usability are **operator-confirmed**,
not independently captured network telemetry or an automated visual assessment.
The screenshots and confirmation were supplied in the development conversation;
they are not committed assets. Local state JSON was not independently inspected.

The reference development source is `ab892a9ea9c344f47258ed32a6f4b34387bba268`,
containing UI integration `b61666d4b04074b9a538881f7e09401150f73f82`.
The operator did not supply the laptop's final Git HEAD or module-path output.
The screenshots show the integrated layout but do not establish an exact local
commit. This documentation record does not claim a new code or model validation.

## Observed results

| Check | Evidence and result |
| --- | --- |
| Automated preflight | Operator pasted `product preflight: automated_pass` and exit code 0. Local report: `D:\ML-runtime\offline-preflight\preflight-13e5wecs\report.json`. The report file itself was not uploaded. |
| Practice Approve | Screenshot shows Approved, 0 awaiting review, 1 simulated decision and 1 profile note. |
| Practice Revise | Screenshot shows Revised, the submitted rationale/replacement wording and 1 profile note. |
| Practice Reject | Screenshot shows Rejected, 0 awaiting review, 1 simulated decision, 0 profile notes and no final wording. |
| Genuine deterministic MCP analysis | Audit screenshot shows four successful actions: `get_competency_evidence`, `read_text_file`, `flag_pattern_for_review`, then a further `get_competency_evidence` read. The view explicitly identifies deterministic orchestration with no Qwen inference. |
| MCP Revise | Screenshot shows Revised, the supplied replacement under Final wording, 0 awaiting review, 1 simulated decision and 1 profile note. |
| MCP Reject | Screenshot shows Rejected, 0 awaiting review, 1 simulated decision and 0 profile notes. |
| Connectivity | Operator confirmed all internet connections were disconnected during the MCP checks. This confirmation specifically covers the MCP portion, not separately timed connectivity for every earlier practice screenshot. |
| Return without saving | Operator confirmed 1 pending / 0 decisions / 0 profile notes after cancellation. |
| Narrow-window presentation | Operator confirmed evidence and decision controls remained readable and usable. No exact viewport dimensions were recorded. |

Screenshot filenames supplied in the conversation:

- `image(20261102-171804).png`: practice Approve.
- `image(20261103-055329).png`: practice Revise.
- `image(20261103-055652).png`: practice Reject.
- `image(20261103-055958).png`: genuine MCP audit.
- `image(20261103-060351).png`: MCP Revise.
- `image(20261103-061048).png`: MCP Reject.

The MCP browser observations cover Revise and Reject. Earlier service-level
acceptance separately covers all three decisions; a new MCP-browser Approve
case is not claimed here.

## Issues retained and interpretation

An earlier preview attempt returned HTTP 403, Cross-origin request blocked.
The operator also reported the old footer wording. Source review found that
the pre-UI build used `no-referrer` and retained that footer, while the integrated
build uses `same-origin` and removes it. An attempted fetch failed with a DNS
resolution error. Subsequent screenshots show successful review submissions and
the integrated layout. The exact initially running commit and rejected Origin
header were not captured, so the initial cause remains an inference rather than
a confirmed diagnosis. Those failed attempts are not recast as passes.

The completed observations establish a bounded, operator-confirmed local
demonstration using genuine deterministic MCP calls and simulated human review.
They do not establish fresh Qwen reliability, semantic correctness, teacher
authentication, classroom impact or real-learner suitability. The displayed
Qwen result remains separately recorded historical evidence. No new model
inference evidence or verified product-version fallback recording was supplied.

The disconnected MCP rehearsal gate is closed on this stated evidence. Exact
release-source provenance and the broader promotion consequences remain part
of final release review; PR #31 remains draft pending explicit promotion sign-off.

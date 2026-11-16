# Development consistency audit — 16 November 2026

## Scope and starting point

The audit started on `product-development` at
`f4aac6087558bee4cf7de4eed85646599aa26102`, after the initial bounded Bedrock
integration. It reviewed the hosted request path, saved-case validation,
teacher workspace, optional authentication dependencies, CI configuration and
current operating documentation. It is a targeted correctness and consistency
review, not an exhaustive security assessment or educational validation study.

No AWS login, provider inference or paid model request was attempted during this
audit. The operator's browser sign-in returned HTTP 400; that does not establish
an AWS service outage, Bedrock invocation permission or a credential-policy cause.

## Corrections and verification scope

| Area | Inconsistency identified | Correction |
| --- | --- | --- |
| Authentication dependencies | The original Bedrock extra allowed an older SDK and omitted the CRT support needed for the supported console-login credential provider. | Require `botocore[crt]>=1.41,<2`; install the Bedrock extra in hosted CI so optional-provider checks are exercised. |
| Request and interruption accounting | A request limit alone did not show whether credentials failed before transmission, a response returned, or the request's remote outcome was unknown. The original deadline covered only the decision stage. | Persist actual HTTP attempt/delivery state, cover the MCP lifecycle with a shared deadline, retain cancellation/termination metadata and keep failure cases readable without manufacturing a candidate. |
| Saved-case consistency | The initial hosted loader did not verify the entire saved provider request/response, decision, evidence and generation-state relationship before enabling review. | Tighten manifest, request/response, current-fixture, candidate and human-state checks; reject inconsistent records before opening review controls. |
| Workspace identity | Shared wording could describe hosted attempts as local Qwen work or imply a request when none reached the provider. | Retain a separate Bedrock identity and use recorded delivery information for the hosted attempt. |
| Current architecture and entry points | The architecture summary omitted browser Qwen review, authored demonstrations and the new hosted CLI. Its generic description of the analysis button could be read as covering every action. | Document each path separately, identify the deterministic MCP action explicitly and distinguish local-Qwen generation from hosted CLI generation and saved reopening. |
| Operator examples and retained artefacts | Bedrock run/open examples used different output roots, and the guide implied every failure retained a response body and usage. | Use one explicit short Windows output root, require the printed case directory on reopening and describe request/response/usage records as stage-dependent. |
| Decision consequences | The hosted workspace description could imply every confirmed decision created a profile note. | State that Approve/Revise retain one synthetic note; Reject retains none. Preview alone records no decision. |

The README now lists the hosted path alongside existing workspace modes and
links its preparation guide beside the local-session instructions. Current
workspace documentation distinguishes a separate hosted CLI request from browser
review of saved local records. Region selection, authentication, invocation
permission and credit coverage remain separate checks; none is inferred from
access to the model catalogue or a browser session.

## Verification

Local verification used the audit working tree over the starting commit above,
with the `[dev,bedrock]` extras installed, Botocore **1.44.3** and CRT
(`awscrt`) **0.38.0**. The changes were uncommitted at the time of those checks;
the publishing pull request will identify the exact final source head and its
separate hosted CI result. These local results must not be attributed to the
starting commit alone.

| Check | Result and scope |
| --- | --- |
| Complete `python -m pytest -q` suite | **1009 passed in 61.65 s**, with no skips; workspace proxy variables were removed only from the test process |
| Bedrock regression scope | **30 collected tests**, included in the complete passing suite; mocked provider transport, synthetic fixtures, local MCP/HTTP and dummy signing credentials |
| `python -m ruff check .` | Passed |
| `python -m pip check` | Passed with the optional Bedrock dependencies installed |
| `git diff --check` | Passed |
| Relative documentation targets | **198 passed**, including **8 heading anchors**, across README, architecture and operating documents |
| Current documentation naming | Generic document names and presentation wording retained across README, architecture, evaluation and `docs/` |

The regressions cover fail-closed request/response and saved-state consistency,
missing mutable state, malformed manifests, credential-provider support, actual
request delivery, interruption, preview without a decision, explicit teacher
confirmation, duplicate rejection and reopening. A failure after a completed
submission is conservatively refused before opening the workspace rather than
presented as a successful completed case. Software tests use fictional evidence
and mocked provider responses; they are not hosted model observations.

Earlier 727-, 940- and 989-test records retain their original scopes. The
[historical source-release record](release-status.md), original challenge
snapshots, committed `evidence/`, failed model outcomes and previously saved
runtime artefacts are not rewritten as audit successes.

## Remaining limits

- Local consistency hashes are not signed provider provenance. Teacher identity
  remains `simulated-teacher-not-authenticated`; the workspace is single-user.
- Bedrock schema delivery remains prompt text. Reasoning configuration remains
  the provider default, separately recorded from a Playground trial with
  reasoning explicitly disabled. Structural validity does not establish that
  a claim is educationally justified.
- Cancelling the credential-resolution await does not stop its background worker
  thread. That worker may finish later, but cannot dispatch the HTTP request
  after the awaiting coroutine has been cancelled. A transmitted request can
  still have an unknown remote outcome after a timeout or cancellation.
- Local SDK authentication, permitted region, credit coverage and invocation
  permission remain to be established before the bounded live integration trial.
  The audit does not repeat the unsuccessful browser sign-in attempt.
- Consistent model judgement, independent educator moderation, real-school
  suitability and measured learning impact remain unestablished.
- Source development is separate from release promotion. This audit does not
  promote `main`, deploy a website or authorise real learner data.

See the [Bedrock operating guide](bedrock-review.md),
[teacher workspace guide](teacher-workspace.md) and
[demonstration walkthrough](demo-walkthrough.md) for their respective scopes.

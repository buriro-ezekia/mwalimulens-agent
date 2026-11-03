# Decision-only schema visibility diagnostic

The saved `runtime/structured_review/v2-1101104704/suite-lttkzu86/longitudinal-pattern/`
probe used `provisional_review_v2` and returned one schema-valid abstention about
consistent improvement or independent mastery. It completed one model request
(102.326 seconds), created no candidate, and recorded no runtime error or
termination. Its result remains a historical failure; this experiment neither
regrades it nor changes the decision policy.

[Ollama's structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs)
recommends including the schema in the prompt as well as supplying it through
`format`. This experiment tests schema visibility as one possible influence on
the model's decision. It does not assume that additional visibility will produce
a candidate or improve judgement.

## Conditions and evidence

- **A:** current `review_messages(snapshot)` and unchanged
  `ReviewDecision.model_json_schema()` supplied through `format`.
- **B:** identical policy, evidence and format schema, with only a clearly
  identified output-contract block appended to the system message. The block is
  the exact format schema serialized with sorted keys. It contains no example
  answer or extra decision instruction.

Both conditions use the unchanged production `OllamaJsonGenerator`: temperature
0, `num_predict=1024`, `stream=false`, the same model/base URL and the same
optional keep-alive setting. No seed, warm-up generation, action tool or retry is
added. The condition messages contain no scenario name, category or expected
outcome.

| Scenario | Evidence source | Execution order |
| --- | --- | --- |
| longitudinal-pattern | Saved probe snapshot, existing hash verified | A then B |
| conflicting-evidence | Complete existing synthetic competency records | B then A |
| single-assessment | Complete existing synthetic competency records | A then B |
| missing-competency | Complete existing synthetic competency records, including empty evidence | B then A |

The L001 snapshot's existing payload SHA-256 is
`19cacb3f7bf1d6331bac13eb4fa6d37e308154170cfb4840e072f0d81fe64543`.
The loader recomputes it with the original snapshot encoder and fails on a
mismatch. It separately records the source file's byte hash. Each case uses one
immutable snapshot for both conditions; the remaining cases use the domain
reader and the existing evidence serializer without opening an MCP client or
creating application state.

## Preparation and bounded live plan

Preparation is offline and is the CLI default:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.schema_visibility_probe --snapshot "runtime/structured_review/v2-1101104704/suite-lttkzu86/longitudinal-pattern/evidence_snapshot.json"
```

Every invocation creates a new `runtime/schema_visibility/cmp-*/` directory.
`plan.json` records the commit, working-tree status, diff/source hashes, policy
ID/text hash, schema hash, evidence hashes, requested model identity, settings
and fixed comparison matrix. Each case contains its full snapshot and the A/B
message/schema inputs. Preparation contacts no model; its model digest remains
explicitly unverified. Existing source and historical output locations are
rejected as output roots.

After separate authorization, the same command with `--run` prepares a fresh
comparison and executes it immediately. It does not replay or overwrite an old
prepared directory. Before any request it verifies that the persisted inputs
match the current policy, schema and snapshots. Complete the context preflight
below before invoking `--run`; the CLI does not establish context fit itself.

The live plan is **at most eight sequential generations: one per condition per
case**, with no repairs or retries. Each request has a 180-second client deadline;
the sum of request deadlines is at most 24 minutes, excluding cleanup, local I/O
and model-identity lookups. The 1024-token per-request ceiling gives at most 8192
requested output tokens. These are diagnostic bounds; production defaults and
budgets are unchanged. A request timeout is recorded as `timed_out`. Timeout or
cancellation persists that condition's outcome and stops further generation.
`comparison.json` explicitly lists the remaining conditions under `not_run`;
an interrupted comparison can end earlier than eight requests. Neither client
timeout nor cancellation proves that provider-side computation has stopped.

At most two read-only `/api/tags` lookups (five-second timeout each), before and
after the generations, record the installed model digest and any identity change.
The final lookup is omitted when generation stops early.
Failure to resolve the starting digest prevents generation. Each decision file
retains the actual HTTP request, provider response, raw output, parsed candidate
contents, validation issues and request metrics. Interrupted or failed requests
remain visible; no result is retried to meet an expected outcome.

The diagnostic owns the underlying transport and response stream. HTTPX borrows
wrappers; reaching the end of the body and exiting the client context do not
close these owned resources before capture.
`run_condition` retains the original outcome, available request/response data,
raw/parsed output and metrics before attempting owned cleanup once, including
when generator construction fails. Cleanup exceptions are recorded separately
under `cleanup_errors`, preserving an earlier timeout or cancellation as the
primary outcome. Each owned resource gets one close attempt even if another
close fails; cleanup errors identify the resource. A cleanup failure also stops
further generation via `stop_reason`, while the condition's original `status`
remains intact. No close is retried. A completed-but-invalid response with successful cleanup remains
recorded and the comparison continues normally.

## Context preflight before an authorized live comparison

Keep the following evidence in a new diagnostic directory, separate from the
original prepared inputs and historical reports. No live preflight or generation
is authorized by this change.

1. Record the Ollama version, installed model digest, model parameters, exact
   prompt template/renderer and matching tokenizer identity/version. Capture
   the relevant server configuration and any context overrides. The
   [model-details API](https://docs.ollama.com/api-reference/show-model-details)
   exposes model details and rendering metadata; the
   [Modelfile reference](https://docs.ollama.com/modelfile) describes templates
   and token parameters.
2. Establish the effective allocated context for that exact model and server
   configuration using the running model's `context_length` from
   [`/api/ps`](https://docs.ollama.com/api/ps), or the `CONTEXT` value in
   [`ollama ps`](https://docs.ollama.com/context-length), together with the
   configuration evidence. A model family's architectural maximum or an
   assumed default does not establish the allocation used by these requests.
   If the model is not loaded and allocation cannot be established without
   additional execution, leave preflight incomplete and seek authorization for
   that separate step; do not add an uncounted warm-up generation.
3. Count all eight complete rendered A/B inputs with the exact matching
   tokenizer and template: policy/system text, full evidence, B's exact schema
   text, role wrappers, special tokens and assistant prefix. Record the method,
   tool version, hashes of the prepared inputs and rendered prompts, and the
   per-condition token counts. Require **input tokens + the unchanged 1024-token
   output allowance <= verified effective context** for every condition.
   Character counts, byte counts or evidence-only token counts are insufficient.
4. Keep any available truncation diagnostics. After an authorized run, compare
   the recorded counts against
   [`prompt_eval_count`](https://docs.ollama.com/api/chat) and provider logs;
   a completed response or that metric alone does not prove the entire input
   survived truncation. Verify that the fresh run's inputs and configuration
   match the preflight evidence.

If exact counting, effective allocation or fit cannot be established, mark
context fit **unverified** and stop before generations. Do not silently increase
`num_ctx`, trim evidence/schema, change production defaults or adjust only one
condition. Any required configuration change needs a separately reviewed,
symmetric plan. Context fit remains unverified for this implementation; mocked
tests cannot establish it.

## Interpretation

All reports explicitly say `decision_only: true`,
`application_workflow_test: false` and `submission_enabled: false`.
The runner has no submission callback and never calls `decide_and_submit`,
`flag_pattern_for_review`, teacher review, profile mutation or the evaluator.
`valid` means the unchanged decision/evidence validator accepted the output;
it is not a semantic verdict. Parsed contents of invalid decisions are retained
for offline inspection. `completed` means all eight planned requests ended
without a stopping timeout, cancellation or cleanup failure; it can include
invalid responses and other recorded runtime errors. It is not a workflow pass
or reliability score. A valid decision followed by cleanup failure keeps its
valid condition outcome, while the comparison reports the reason it stopped.

Review A/B decisions and their qualifications, counter-evidence, abstention
reasons, validation issues and timings for **all four cases**, including sparse
and missing-evidence controls. Keep wording quality separate from structural
validity. One paired observation per case cannot establish a causal improvement
or reliability rate; order, caching and model variability remain limitations.
Deterministic mocked tests verify experimental isolation and non-submission,
not improved live-model judgement. No live comparison has been run by this change.

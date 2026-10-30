# Structured candidate workflow (opt-in; live reliability not yet verified)

## Why this path exists

The saved `suite-xrlcv_u0` completed within its execution deadline but failed:
Qwen requested `flag_pattern_for_review`, received retry feedback, then said
that the claim and teacher question were missing. No candidate reached the
service audit. The uploaded report does not retain the raw rejected arguments,
so it cannot alone establish the exact validation error.

The new path separates **model interpretation** from **application submission**.
It is not another regex-triggered prompt retry, and it does not replace the
existing free-form tool-calling runner.

1. The application retrieves complete competency evidence through the genuine
   Education MCP client and verifies target identity, source references and IDs.
   The complete immutable snapshot and its SHA-256 are saved per run.
2. Qwen returns an explicit `candidate` or `abstain` decision through Ollama's
   native `/api/chat` JSON-schema `format` option. No action tools are exposed
   to this model request. A candidate contains all seven existing MCP fields.
   Claim, uncertainty and teacher question are model-authored outputs, not
   presumed missing inputs from the user.
3. Pydantic and source-based validation reject missing/empty fields, extra fields,
   out-of-scope IDs, overlapping roles, duplicate IDs and supporting evidence
   that does not span terms. At most one proposal repair is permitted. No
   missing content is fabricated. Genuine abstention remains possible.
4. Only a validated model-authored candidate authorises the application controller
   to call `flag_pattern_for_review`. There is at most one submission attempt;
   an ambiguous write failure is never blindly retried. The confirmed audit
   must match the complete candidate and remain `pending_teacher_review`.
5. The existing scenario rubric grades the persisted state. The original
   historical suites, evidence fixtures and teacher authority are unchanged.

Ollama's structured output capability is documented at:
https://docs.ollama.com/capabilities/structured-outputs
https://ollama.com/blog/structured-outputs
Native JSON-schema formatting is not proof that the interpretation is true.

## Honest provenance and evaluation

Reports use `workflow_mode: structured_proposal_v1`,
`submission_actor: application_controller` and
`model_tool_selection_evaluated: false`. The model's tool allowlist is empty;
the application MCP allowlist is reported separately. A pass is a system
workflow result, **not** evidence that Qwen autonomously selected and called
the action tool. Do not combine it with the legacy tool-selection accuracy.

An invalid initial proposal is retained as a failed initial stage even when
proposal repair later succeeds. Native request success is labelled `returned`,
not treated as evidence validation. Structural pass/fail, semantic cautions,
manual teacher review and historical failures remain separate. Missing or
invalid proposals cannot be relabelled as successful evidence-based abstention.

The current structural rubric requires supporting and counter-evidence; this
path keeps that rule. It does not prove the relevance of the counter-evidence,
assessment comparability, instructional usefulness or classroom effectiveness.
The original scenario semantic warnings and human review remain necessary.

## Execution limits and safety

The existing outer suite runner still enforces a 600-second watchdog and at
least 30 seconds of margin. One 540-second internal deadline covers retrieval,
preload, generation, validation, submission and cleanup. The request budget is
shared; this path needs at most two proposal requests, even if the configured
shared limit is larger. All five artefact paths (state, report, result, evidence
snapshot and progress checkpoint) must be distinct and absent before execution.
Existing snapshots and checkpoints receive the same protection as final reports.

Cancellation produces a failed report and result and propagates; it is not
converted into a model abstention. External cancellation during cleanup after a
deadline preserves the original deadline termination and writes final reports
before propagating, including when cleanup raises another exception.
Checkpoints record active stages and preserve
completed outcomes. No prompts, arguments or private reasoning are copied into
request telemetry. The complete synthetic evidence and validated candidate
remain in the ordinary case artefacts. No school or real-pupil deployment is
permitted by this change. Provider-side compute cancellation remains unverified.

## Verification before live inference

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

The new contract tests include the exact missing-claim/missing-teacher-question
shape, malformed/prose-only decisions, invalid evidence, genuine abstention,
no-write-before-validation, schema transmission, truncation and ambiguous writes.
Integration tests use genuine in-process MCP but mocked model responses. They
are not live Qwen evidence.

Local review reproduced three defects: an undeclared `httpx` import prevented
test collection; derived snapshot/checkpoint paths could overwrite existing
artefacts or collide with explicit paths; and cancellation during cleanup after
a deadline could skip final reports or be swallowed. The corrections declare
`httpx>=0.28,<1`, check all five paths before execution, and distinguish external
cancellation after timeout cleanup. Six added regression cases reproduced the
path and cancellation defects before correction.

On the corrected code, Ruff and `pip check` passed, the focused contract/MCP/
cleanup suite passed 45 tests, and the complete suite passed 539 tests. An earlier
complete run had 532 passes and one `ConnectionAbortedError [WinError 10053]` in
`test_nonexistent_route_does_not_mutate`; that test passed on focused retry and
in the final complete run without portal changes. Local tests used Python 3.14,
PydanticAI 2.51.0, FastMCP 4.0.10, MCP 2.2.0 and HTTPX 0.28.1.

These local results do not establish the cause of historical CircleCI failures
#107/#108, whose failing logs were unavailable. Consult PR #33 for the current
commit's hosted status. Live-model reliability, provider-side cancellation and
semantic correctness remain unverified; no live Ollama/Qwen run was performed.

Only after review and passing local/hosted checks, a single explicitly approved
probe can be run with:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.structured_review --timeout 600 --scenarios longitudinal-pattern
```

The output is stored separately under `runtime/structured_review/suite-*/`.
Read its `summary.json`, `<scenario>/report.json` and `<scenario>/result.json`.
The legacy `mwalimulens.multi_scenario_eval` remains unchanged for comparison.
Do not claim the reliability problem is solved until actual local Qwen results
and semantic review establish that the revised workflow meets its requirements.

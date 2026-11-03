# Audited model-request sequence and concise prompt experiment

MwalimuLens now identifies which audited MCP tool calls had completed before
each Qwen request started. This allows a model-request row to be interpreted
without logging learner evidence or copying model-generated content into
performance telemetry.

## Interpretation

In `runtime/open_weights_run.json`, inspect `model_requests`. Each row has:

- `request`, `status`, `seconds`, and available token counts.
- `audited_tools_before`: names of MCP operations already audited when
  the model request began.
- `audited_tools_after`: names audited when that model request ended.

Most agent tool calls occur **between** model requests. For example, if request
2 begins after `get_competency_evidence` and request 3 begins after
`flag_pattern_for_review`, then request 2 generated the tool-request
decision or parameters that led to the pending candidate. It does **not**
prove that every generated token was necessary or corresponded to user-facing
prose. Duration remains per-request wall time rather than native generation
time. Tool calls may be absent on failed requests or delayed in some workflows.

The audit checkpoint contains **tool names only**, not student evidence,
prompts, identities, candidate wording or hidden model reasoning. The
existing full run report still contains evaluation material; do not publish
a real-student report.

## Two prompt styles

- `baseline` (default): preserves the original full task prompt.
- `concise`: an explicitly opt-in shorter task prompt. It retains the
  evidence-first requirement, exact supporting/counter-evidence IDs,
  uncertainty, a teacher question, abstention on insufficient evidence
  and a strict prohibition on autonomous teacher approval or permanent
  learner labels. The system-level MCP allowlist and review gate are unchanged.

Run on the same CPU machine, using distinct runtime JSON files:

```powershell
git pull --ff-only origin product-development
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .

.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run --keep-alive 30m --prompt-style baseline --report runtime/baseline-latest.json
.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run --keep-alive 30m --prompt-style concise --report runtime/concise-latest.json
```

Those single runs are diagnostics, **not** enough for a reliable speed
comparison. Run repeated evaluations to retain all successes and failures:

```powershell
$env:MWALIMULENS_OLLAMA_KEEP_ALIVE = "30m"
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --runs 3 --timeout 600 --prompt-style baseline
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --runs 3 --timeout 600 --prompt-style concise
Remove-Item Env:\MWALIMULENS_OLLAMA_KEEP_ALIVE
```

For every campaign inspect `summary.json` and each
`attempt-*/report.json`. Compare pass/fail counts, human-gate violations,
completion recovery, tool failures, per-request output-token counts and
p50/p95 elapsed time; compare like-for-like warm runs when possible.

**Do not adopt the concise prompt as default** until the evidence-backed
candidate quality and teacher-review gates remain sound across more
fictional scenarios and repeated runs. A reduced runtime without the
required supporting/counter-evidence is a failed optimisation.

The historical comparison points are 275.926 seconds for the initial
instrumented run and 328.386 seconds for a later keep-alive run, with
three requests of 49.21s, 201.04s and 58.61s. These are distinct local
observations, not controlled paired benchmarks.

# Local Ollama performance controls

MwalimuLens provides opt-in model preloading and per-request model telemetry.
Its default execution and the existing teacher-approval boundary are unchanged.

## Preload Qwen for an instrumented run

From the repository root in PowerShell:

```powershell
git pull --ff-only origin product-development
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run --keep-alive 30m
```

The `--keep-alive` option requests a local model preload through Ollama's
native `/api/generate` API with an empty prompt. Accepted positive durations
are in seconds (`s`), minutes (`m`) or hours (`h`), with a maximum of one
hour. Without a configured duration, MwalimuLens does not initiate preloading.

You can configure the same setting across isolated reliability processes:

```powershell
$env:MWALIMULENS_OLLAMA_KEEP_ALIVE = "30m"
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --runs 3 --timeout 600
Remove-Item Env:\MWALIMULENS_OLLAMA_KEEP_ALIVE
```

Only loopback addresses are eligible for the preload request. Failed
preloading prevents that instrumented task from continuing and is included
in its failed run report. Ollama's subsequent OpenAI-compatible requests may
follow the **server's** retention policy, so preloading is not a guarantee
that all subsequent calls inherit the specified keep-alive duration. Use
`ollama ps` to inspect the current runner.

## Telemetry fields

Each `runtime/open_weights_run.json` report records:

- `preload`: status, whether attempted, requested duration and elapsed time.
- `model_requests`: one entry for each observed model request with a
  sequential index, status, elapsed wall-clock seconds, and provider-reported
  input, output and total token counts when exposed by PydanticAI.
- `model_request_count_observed`: number of captured model request records.
- `timing`: construction, initial agent, optional recovery and total workflow
  timings, plus the existing service-side Education MCP call durations.
- `checks`: the unchanged evidence-grounding and human-review checks.

Provider token usage is not guaranteed; absent counters remain null.
Per-model-request durations include client, transport and model processing
time. **They are not pure token-generation durations**, nor the native Ollama
`load_duration`, `eval_duration` or `prompt_eval_duration`. No prompts
or model responses are duplicated into telemetry records.

Read the latest report with:

```powershell
$r = Get-Content runtime\open_weights_run.json -Raw | ConvertFrom-Json
$r.preload | Format-List
$r.model_requests | Format-Table -AutoSize
$r.timing | Format-List
$r.checks | Format-List
```

The reliability campaign additionally aggregates known request counts and
token totals across attempts in `runtime/model_reliability/campaign-*/summary.json`.
Individual `attempt-*/report.json` files retain each model request record.

## Baseline and acceptance

The measured pre-optimisation full-workflow baseline was 275.926 seconds
for one Qwen2.5 3B local CPU run. The earlier three-run reliability campaign
passed three of three attempts, with zero observed teacher-gate violations.
These are **historical observations**, not guaranteed future timings.

Compare the new full agent results with the baseline, preserving the same
model, fictional learner scenario, evidence-ID requirements, counter-evidence,
tool success and no-autonomous-teacher-review checks.

A warm-model improvement in a short single-prompt benchmark cannot be
extrapolated directly to the full agent. If any run fails or gate checks
change, do not promote the optimisation as a product improvement.

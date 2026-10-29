# Model and MCP workflow timing

MwalimuLens now records **stage-level elapsed times** during local Qwen execution.
This is diagnostic instrumentation, not a claim of faster inference.

## Measurements

The JSON report from `mwalimulens.agent.open_weights_run` includes a `timing`
object with:

- `agent_build_seconds`: elapsed time to construct the local PydanticAI agent.
- `initial_agent_run_seconds`: the initial agent operation, including
  model inference, orchestration and its MCP calls.
- `recovery_agent_run_seconds`: the optional bounded recovery turn; null
  when recovery is not attempted.
- `total_wall_seconds`: elapsed time from run setup until the outcome
  report is assembled, excluding subsequent JSON write time.
- `model_only_seconds` and `model_load_seconds`: explicitly null
  because the present integration does **not** measure them directly.
- `tool_call_summary[*].duration_seconds`: service-side elapsed
  execution time for each custom Education MCP call, where available.

Each duration is measured with a monotonic timer; audit timestamps remain
timezone-aware wall-clock values. Existing historical reports are not
retroactively populated. An older report without this schema remains valid.

The custom MCP tool durations measure code-side service execution; they
do not include the complete request/response transport or model time.
The overall agent-run span must **not** be relabelled as model-only inference.
Subtracting service durations from agent-run time does not yield a verified
model-only duration because other orchestration and transport costs remain.

## Run a real instrumented task

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run
```

Inspect the generated `runtime/open_weights_run.json` and its `timing` and
`tool_call_summary` fields. This writes local runtime evidence, not the
previously promoted challenge evidence.

For a repeated campaign, continue using:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --runs 3 --timeout 600
```

The repeated-run harness records full per-attempt JSON files in separate
directories. Inspect the individual `report.json` timing fields rather
than treating the aggregate subprocess duration as pure model latency.

## Validation and responsible optimisation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Before changing model size, prompts, quantisation or caching, compare multiple
runs and require the existing evidence-ID, counter-evidence, candidate and
human-review gate checks to continue passing. Preserve failed attempts and
do not infer classroom effectiveness from throughput alone.

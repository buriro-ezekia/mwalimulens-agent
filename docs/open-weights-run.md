# Local Qwen / Ollama open-weights run

This workflow produces the judge-facing evidence for the challenge requirement that one complete
agent task run on an open-weights model.

MwalimuLens defaults to:

- provider: Ollama;
- model: `qwen2.5:1.5b`;
- endpoint: `http://localhost:11434/v1`;
- agent MCP allowlist: `get_learner_timeline`, `get_competency_evidence`,
  `flag_pattern_for_review`.

The model never receives `record_teacher_review`.

## Why Qwen2.5 1.5B

The project uses the small local model already available in the development environment.
Ollama lists Qwen2.5 1.5B as a tool-capable Qwen2.5 variant, so it can exercise the real MCP
workflow without requiring a larger model download.

The model name remains configurable. If the 1.5B model produces an honest tool-calling failure,
preserve that result for later evaluation and retry with a stronger local Qwen model rather than
weakening the safety checks.

## 1. Prepare the project environment

Use the repository-local virtual environment:

```powershell
if (!(Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
```

Expected dependency result:

```text
No broken requirements found.
```

## 2. Confirm Ollama and Qwen

```powershell
ollama list
```

If `qwen2.5:1.5b` is not present:

```powershell
ollama pull qwen2.5:1.5b
```

Make sure the local Ollama service is running before the task.

## 3. Run the complete open-weights task

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run
$LASTEXITCODE
```

A successful run exits with code `0`.

The runtime report is written to:

```text
runtime/open_weights_run.json
```

A failed run is still written to that path with `"status": "fail"` and an error/check summary.

## 4. Required passing checks

The report can only have `"status": "pass"` when all of these are true:

- the endpoint is local;
- the model name is Qwen;
- the target L001 / MATH-FRACTIONS evidence was retrieved through MCP;
- `flag_pattern_for_review` was called;
- all audited MCP calls succeeded;
- `record_teacher_review` was not called;
- a pending teacher-review candidate was created for L001 / MATH-FRACTIONS;
- that candidate cites both supporting and counter-evidence;
- the model produced a non-empty final response;
- no teacher review occurred; and
- no profile update occurred.

The report stores no hidden chain-of-thought.

## 5. Promote only passing evidence

After inspecting the runtime report:

```powershell
Get-Content runtime\open_weights_run.json
.\.venv\Scripts\python.exe -m mwalimulens.agent.promote_open_weights_evidence
```

Promotion is blocked unless the report is a passing local Ollama open-weights run with every
evidence/safety check true.

A successful promotion creates:

```text
evidence/open_weights_run.json
```

That file is intended to be committed so challenge reviewers can inspect the real run after
cloning the repository.

## Optional model override

For a different local Qwen model:

```powershell
$env:MWALIMULENS_OLLAMA_MODEL = "qwen2.5:3b"
.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run
```

Or use the CLI flag:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.agent.open_weights_run --model qwen2.5:3b
```

The same model-facing MCP safety boundary is used regardless of which local Qwen model is chosen.

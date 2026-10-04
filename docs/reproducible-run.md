# Reproducible one-command run

The judge-facing clean-checkout command is:

```powershell
python scripts/run_challenge.py
```

## External prerequisites

The bootstrap intentionally does not install system-level software or download a large model.

Required before running:

- Python 3.11 or newer;
- Node.js 20 or newer and npm;
- Ollama running on the local machine; and
- `qwen2.5:3b` installed in Ollama.

For the default local setup:

```powershell
ollama pull qwen2.5:3b
```

The Ollama OpenAI-compatible endpoint defaults to `http://localhost:11434/v1`.

An alternative local endpoint can be supplied without editing repository files:

```powershell
python scripts/run_challenge.py --base-url http://127.0.0.1:11434/v1
```

## What the single command does

The bootstrap uses only the Python standard library before project installation.

It then:

1. validates Python >= 3.11;
2. creates or reuses the repository-local `.venv`;
3. installs the MwalimuLens Python package into that virtual environment;
4. validates Node >= 20 and npm;
5. runs `npm ci` from the committed lockfile;
6. checks that Ollama is local and that `qwen2.5:3b` is installed;
7. runs the real local Qwen longitudinal task;
8. runs the official borrowed Filesystem MCP read-only smoke;
9. runs the 13-case reliability evaluation; and
10. writes a concise final PASS/FAIL report.

The bootstrap does **not** approve, edit or reject a learner candidate. A successful open-weights
step must still end with a pending teacher-review candidate and zero teacher reviews/profile
updates.

## Runtime outputs

The consolidated report is:

```text
runtime/challenge_run.json
```

Detailed component reports are:

```text
runtime/challenge_open_weights_run.json
runtime/challenge_borrowed_mcp_run.json
runtime/challenge_borrowed_mcp_stderr.log
runtime/challenge_evals_run.json
```

The consolidated report records compact environment metadata, component status, report paths and
the human-gate check. The detailed component files retain auditable tool evidence.

## Failure behaviour

The command exits non-zero when a required step fails.

Common prerequisite messages are explicit:

- unsupported Python -> install/use Python 3.11+;
- unsupported/missing Node or npm -> install Node 20+ with npm;
- Ollama unavailable -> install/start Ollama locally;
- `qwen2.5:3b` absent -> run `ollama pull qwen2.5:3b`.

The bootstrap does not silently fall back to a cloud model or a different Ollama model.

## Evidence promotion

After a real one-command PASS, promote the consolidated report:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.promote_challenge_run
```

Only a report with every required check true can become
`evidence/challenge_run.json`.

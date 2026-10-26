# Continuous integration with CircleCI

MwalimuLens uses a CircleCI configuration at `.circleci/config.yml` on the
`product-development` branch to automate its existing code-quality checks.

## Checks

The job runs on CircleCI's Python 3.13 + Node convenience image and executes:

```bash
python -m pip install --disable-pip-version-check -e ".[dev]"
python -m pip check
npm ci --no-audit --no-fund
python -m pytest -q
python -m ruff check .
```

The `npm ci` step installs the pinned official Filesystem MCP server. This
pipeline is designed to verify the 367-test repository baseline and linting;
the number of tests may change as the product develops.

The job is deliberately **not** a live Qwen/Ollama benchmark, a classroom
validation, a hosted product deployment or proof that the Windows recording
workflow works. It runs in a Linux container with no Ollama or OBS service.

## Enable CircleCI

1. Sign in at https://app.circleci.com/ and connect your GitHub account.
2. Add the `buriro-ezekia/mwalimulens-agent` repository as a CircleCI project.
3. Select the existing `.circleci/config.yml` file on the
   `product-development` branch as the configuration source, if prompted.
4. Configure the repository/branch trigger for `product-development`, then
   run the first pipeline.
5. Inspect both the pytest and Ruff steps. Record the pipeline URL and
   whether the job actually passed.

GitHub App and OAuth projects may use slightly different configuration and
trigger screens. Follow CircleCI's repository onboarding rather than
creating a second or duplicated configuration file.

## Local parity

For Windows, the equivalent checks remain:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git status --short
```

A locally passing test suite does not prove that the CircleCI job ran.
Likewise, a successful Linux CircleCI job does not replace local/offline
browser and genuine MCP integration checks on the intended device.

Keep secrets out of YAML and Git. This job does not need any application API
keys or external credentials. Do not configure deployment or automatic
publishing until product-specific security and release gates are established.

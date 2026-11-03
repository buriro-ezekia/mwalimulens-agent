# Continuous integration with CircleCI

MwalimuLens uses the committed `.circleci/config.yml` to automate its code-quality
checks. It is included in the source release and maintained on `product-development`.
Repository connections and branch triggers are configured separately in CircleCI;
the YAML alone does not prove that a particular branch or commit has run.

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
pipeline runs the complete suite collected from its checked-out commit and Ruff.
The integrated UI baseline has 727 operator-reported local passes. GitHub reports
`ci/circleci: quality` success for integrated commit
`b61666d4b04074b9a538881f7e09401150f73f82` at
[CircleCI #118](https://circleci.com/gh/buriro-ezekia/mwalimulens-agent/118).
The [release record](release-status.md) separates this hosted status from local
test counts and earlier results. Test totals may change as the product develops.

The job is deliberately **not** a live Qwen/Ollama benchmark, a classroom
validation, a hosted product deployment or proof that the Windows recording
workflow works. It runs in a Linux container with no Ollama or OBS service.

## Configuration and trigger checks

CircleCI is already configured for this repository. The setup steps below are
reference instructions for restoring a missing connection; do not create a
duplicate project to repeat a completed quality run.

1. Sign in at https://app.circleci.com/ and connect your GitHub account.
2. Add the `buriro-ezekia/mwalimulens-agent` repository as a CircleCI project.
3. Select the existing `.circleci/config.yml` file as the configuration source,
   if prompted.
4. Check triggers for the intended development or release branch, then inspect
   the pipeline created for the exact commit.
5. Inspect both the pytest and Ruff steps. Record the pipeline URL and
   whether the job actually passed.

GitHub App and OAuth projects may use slightly different configuration and
trigger screens. Follow CircleCI's repository onboarding rather than
creating a second or duplicated configuration file.

A successful GitHub commit status establishes the reported job outcome, not
whether its event was a repository push or a manual/API trigger. Inspect the
pipeline event before claiming automatic push-trigger configuration. Check each
new commit independently; an earlier passing job is not evidence for a later head.

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

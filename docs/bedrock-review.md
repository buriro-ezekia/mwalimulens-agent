# Bounded Bedrock review

This optional path sends one synthetic fractions evidence snapshot through
Bedrock Converse, then applies the existing outcome-bound decision validator
and application-owned MCP submission. It creates no teacher decision itself.
Local Ollama results and authored demonstrations remain separate.

## Preparation without inference

Install or upgrade the optional signing dependencies in the repository environment.
The Bedrock extra includes a current Botocore release and its CRT dependency so
that SDK credentials can also be resolved from a supported `aws login` session:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade -e ".[bedrock]"
.\.venv\Scripts\python.exe -m mwalimulens.bedrock_review --help
```

Configure credentials externally through the AWS credential provider chain,
using an organiser-approved profile or temporary credentials. Never paste keys
into source, model prompts, this chat or saved artefacts. No inference occurs
on import, installation, help or saved-case reopening. A browser console session
does not itself configure local SDK credentials. Successful CLI authentication
also does not establish Bedrock invocation permission or credit coverage. A
browser login error is a separate authentication observation, not proof of an
inference outage.

## One controlled request

Only after confirming credit coverage and the permitted region, run the command
below. Replace the region if the organiser approves a different one.

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.bedrock_review --run `
  --region eu-north-1 `
  --output-root "D:\ML-runtime\bedrock" `
  --credit-and-region-confirmed
```

The switch records an operator assertion, not an AWS billing check. Access to
Playground does not establish API credentials, invocation permission or credit
coverage. The command prints the new unique case directory. It sends at most
one request, disables automatic retries and repairs, and exits after saving its
outcome. A timeout leaves the provider outcome unknown; do not automatically
repeat it. The deadline covers the MCP lifecycle as well as generation.
Credential resolution runs in a background thread that may outlive cancellation;
once its await is cancelled, the coroutine cannot dispatch the HTTP request.
This does not stop computation for a request already transmitted to the provider.
A candidate is not a guarantee or required outcome.

The target is `qwen.qwen3-32b-v1:0`. The request specifies temperature 0,
Top P 1 and maximum output 1024. The schema is supplied as prompt text, not
native constrained decoding. Reasoning configuration is left at the provider
default; this differs from a Playground trial explicitly configured with
reasoning off. Non-text response blocks, abnormal stop reasons, truncation,
fenced JSON and missing fields are rejected without normalisation or insertion.
No action tools are exposed to the model.

## Inspect, confirm and reopen

Use the exact printed directory in place of the example below:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.bedrock_review --open "D:\ML-runtime\bedrock\bedrock-CASE_ID"
```

The run example explicitly selects `D:\ML-runtime\bedrock`. If `--output-root`
is omitted, the default is the repository's `runtime/bedrock`. In either case,
copy the exact case directory printed by that run into the `--open` command.
The workspace labels the case as a hosted Bedrock review. Inspect the model's
wording, evidence references and uncertainty. A technically valid claim may
still overstate competence or misrepresent older observations as current.
Only a pending valid candidate offers review controls. Choose revise, enter
your own reason and final wording, inspect the confirmation page, then explicitly
confirm once. The local reviewer identity is simulated, not authenticated.

Close the workspace and repeat the same `--open` command. Check the same case
ID, review ID, saved reason, final wording and exactly one synthetic profile note.
Do not submit a second decision. Abstentions and rejected responses retain
no review controls. Reopening never invokes Bedrock. Saved Bedrock cases are
opened with this command; they are not listed as local Qwen reviews.

## Saved evidence and limits

Each case retains its terminal outcome, validation events, original generation
state and local SHA-256 receipt. The logical request JSON before signing,
received HTTP response body, provider status/usage/latency, retrieved evidence
and raw decision are retained when those stages complete. Failure before a
response arrives cannot produce a response body or usage record. Credentials,
signed headers and SDK/transport exception strings are not persisted; received
provider error bodies remain part of the saved response.
The receipt checks local consistency; it is not signed provider provenance.
The loader checks the candidate against the saved raw decision and accepts only
the original state or one consistent audited simulated teacher decision.

Offline regression tests exercise a mocked HTTP provider and real in-process
MCP retrieval/submission, plus teacher-state persistence and reopening. These
are application checks, not hosted inference or educator moderation. No live
Bedrock trial has yet been performed by this integration. The previous invalid
Playground candidate and original local abstention remain historical evidence.

API references: [Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
and [Qwen3 32B model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-32b.html).

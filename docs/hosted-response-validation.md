# Hosted response rejection check

On 16 November 2026, the operator pasted a response reported from the Bedrock
Playground with Qwen3 32B selected. It proposed a fractions candidate for the
fictional evidence but omitted the required `candidate.learner_id` field.
The pasted text also included Markdown fences. Provider response bytes, usage,
latency and final generation settings were not independently captured here.

The [regression fixture](../tests/fixtures/hosted_missing_learner_id.txt) preserves
the response text as pasted, with a final newline for the repository file.
It is not a signed provider export or a new model response. The original local
Qwen abstention remains separate and unchanged.

## Verification

The [MCP regression tests](../tests/test_structured_review_mcp.py) replay this
text through the existing structured workflow, with real in-process MCP retrieval
of the synthetic fractions evidence and a stubbed generator. One response is
permitted; no inference, network request, repair or automatic field insertion occurs.
The outcome-bound schema is used.

| Input | Validation issue | Pending reviews | Teacher decisions | Profile updates |
| --- | --- | --- | --- | --- |
| Response as pasted, including fences | `decision: json_invalid` | 0 | 0 | 0 |
| JSON body alone, diagnostic test variant | `candidate.learner_id: missing` | 0 | 0 | 0 |

Both tests require `invalid_proposal`, a recorded `ProposalRejected` error,
exact preservation of the replayed response and its SHA-256 hash, and no submission
event. The only MCP operation is `get_competency_evidence`;
`flag_pattern_for_review` is never called. Removing fences in the second test
isolates the missing-field failure; it adds no production normalisation behaviour.

The existing validator already rejects these inputs. No production policy,
prompt, schema, profile behaviour or validation threshold needed changing.
This verifies an application gate, not the educational quality of the claim,
model reliability, authenticated teacher moderation or a Bedrock-to-workspace
integration. The full teacher confirmation and saved-case reopening sequence
remains incomplete for this hosted observation.

To repeat the offline regression in PowerShell from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_structured_review_mcp.py -k hosted_missing
```

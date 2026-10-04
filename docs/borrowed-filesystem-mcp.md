# Borrowed official Filesystem MCP

MwalimuLens reuses the official Model Context Protocol Filesystem server as the challenge's MCP
server not written by the team.

## Upstream dependency

- Package: `@modelcontextprotocol/server-filesystem@2026.8.31`
- Publisher/project: Model Context Protocol / LF Projects
- Repository: `modelcontextprotocol/servers`
- Licence: MIT
- Transport: stdio

The version is pinned so judges reproduce the same tool schemas and annotations.

Install the pinned borrowed dependency once at repository root:

```powershell
npm ci
```

MwalimuLens then launches the installed upstream JavaScript entrypoint directly with Node:

```text
node node_modules/@modelcontextprotocol/server-filesystem/dist/index.js <reference-dir>
```

The direct Node launch is intentional on Windows: it avoids the `npx.cmd` / `cmd /c` wrapper
between the MCP client and the server's stdin/stdout pipes.

The official Filesystem server is built on the handshake-era JavaScript MCP SDK. FastMCP 4 clients
default to `mode="auto"`, which probes the newer `server/discover` protocol before falling back.
For this borrowed stdio server, MwalimuLens therefore constructs a dedicated FastMCP client with
`mode="legacy"` so the connection begins directly with the standard `initialize` handshake.

## Why reuse this server

Generic filesystem access is not education-domain logic. Reimplementing file reading, directory
sandboxing and filesystem MCP schemas inside MwalimuLens would duplicate infrastructure that an
official MCP server already provides.

MwalimuLens therefore owns the parts that are specific to the product:

- learner evidence identity and retrieval;
- candidate-pattern persistence;
- tool-call audit state;
- teacher approve/edit/reject workflow; and
- human-gated profile consequences.

The borrowed server supplies only generic access to local classroom/curriculum reference files.

## Reference versus learner evidence

The borrowed filesystem contains synthetic classroom reference material under
`data/reference/`.

Reference material may help interpret a competency or formulate a teacher question, but it is
**not learner evidence**. Learner-pattern claims must still cite Education MCP evidence IDs.

## Read-only boundary

The upstream server exposes read and write tools. MwalimuLens applies an explicit model-facing
allowlist:

```text
read_text_file
read_multiple_files
list_directory
search_files
get_file_info
list_allowed_directories
```

The filter also requires the upstream MCP annotation `readOnlyHint=true`.

Tools such as `write_file`, `edit_file`, `create_directory` and `move_file` are never
model-visible.

The upstream process is additionally sandboxed to the configured reference directory.

## Auditing borrowed calls

Every borrowed tool call is wrapped client-side and added to the same MwalimuLens JSON audit
state. Each event records:

- call ID;
- borrowed toolset ID;
- source = `borrowed_mcp`;
- tool name;
- inputs;
- output or error; and
- timestamp.

This keeps the challenge's tool-action audit requirement intact even though the server itself is
external.

## Real smoke run

Install the pinned npm dependency, then run the upstream server through the MwalimuLens smoke
harness:

```powershell
npm ci
.\.venv\Scripts\python.exe -m mwalimulens.agent.borrowed_mcp_run
$LASTEXITCODE
Get-Content runtime\borrowed_mcp_run.json
```

The smoke runner uses a deterministic local FunctionModel so no cloud model/API key is needed. It
must start the official npm server, expose exactly the read-only allowlist, execute
`read_text_file` against the synthetic fraction reference, and verify that the call was audited.

A successful run returns exit code `0` and `"status": "pass"`. The report also records the
installed package version, the explicit legacy client mode and the tail of the upstream server
stderr log so initialization failures remain inspectable.

Promote only a passing report:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.agent.promote_borrowed_mcp_evidence
```

That creates `evidence/borrowed_mcp_run.json` for judge inspection.

The real local smoke run passed with all sandbox, read-only, audit and protocol checks true. The
promoted report is committed at `evidence/borrowed_mcp_run.json`, so the borrowed-MCP challenge
requirement is Present.

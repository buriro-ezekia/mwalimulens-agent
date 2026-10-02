"""Official borrowed Filesystem MCP integration with a read-only agent boundary."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from mwalimulens.mcp_server.server import DEFAULT_STATE_PATH, PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore

BORROWED_FILESYSTEM_PACKAGE = "@modelcontextprotocol/server-filesystem@2026.8.31"
BORROWED_FILESYSTEM_TOOLSET_ID = "borrowed-official-filesystem-mcp"
DEFAULT_REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"

BORROWED_FILESYSTEM_TOOL_ALLOWLIST = frozenset(
    {
        "read_text_file",
        "read_multiple_files",
        "list_directory",
        "search_files",
        "get_file_info",
        "list_allowed_directories",
    }
)

BORROWED_FILESYSTEM_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "create_directory",
        "move_file",
    }
)


def filesystem_stdio_spec(
    reference_dir: Path = DEFAULT_REFERENCE_DIR,
    *,
    windows: bool | None = None,
) -> tuple[str, list[str]]:
    """Return the pinned upstream filesystem-server stdio command."""

    reference_dir = reference_dir.resolve()
    if not reference_dir.is_dir():
        raise ValueError(f"reference directory does not exist: {reference_dir}")

    windows = os.name == "nt" if windows is None else windows
    package_args = [
        "npx",
        "-y",
        BORROWED_FILESYSTEM_PACKAGE,
        str(reference_dir),
    ]
    if windows:
        return "cmd", ["/c", *package_args]
    return "npx", package_args[1:]


def borrowed_tool_is_read_only(_ctx: Any, tool_def: Any) -> bool:
    """Expose only explicitly allowed tools carrying the upstream read-only annotation."""

    annotations = ((tool_def.metadata or {}).get("annotations") or {})
    return (
        tool_def.name in BORROWED_FILESYSTEM_TOOL_ALLOWLIST
        and annotations.get("readOnlyHint") is True
    )


def build_borrowed_audit_callback(state_path: Path):
    """Build an audit wrapper for calls made through the borrowed MCP server."""

    state_store = JsonStateStore(state_path)

    async def audit_tool_call(
        ctx: Any,
        call_tool: Any,
        name: str,
        tool_args: dict[str, Any],
    ) -> Any:
        del ctx
        timestamp = datetime.now(UTC).isoformat()
        call_id = f"borrowed-{uuid4()}"

        try:
            result = await call_tool(name, tool_args)
        except Exception as exc:
            state_store.record_tool_call(
                {
                    "call_id": call_id,
                    "toolset_id": BORROWED_FILESYSTEM_TOOLSET_ID,
                    "source": "borrowed_mcp",
                    "tool_name": name,
                    "status": "error",
                    "timestamp": timestamp,
                    "inputs": tool_args,
                    "output": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            raise

        state_store.record_tool_call(
            {
                "call_id": call_id,
                "toolset_id": BORROWED_FILESYSTEM_TOOLSET_ID,
                "source": "borrowed_mcp",
                "tool_name": name,
                "status": "success",
                "timestamp": timestamp,
                "inputs": tool_args,
                "output": _json_safe(result),
                "error": None,
            }
        )
        return result

    return audit_tool_call


def build_borrowed_filesystem_toolset(
    *,
    reference_dir: Path = DEFAULT_REFERENCE_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
):
    """Build the official filesystem MCP, sandboxed and filtered to read-only tools."""

    command, args = filesystem_stdio_spec(reference_dir)
    audit_tool_call = build_borrowed_audit_callback(state_path)

    transport = StdioTransport(
        command=command,
        args=args,
        env=dict(os.environ),
        cwd=str(PROJECT_ROOT),
        keep_alive=False,
    )
    raw_toolset = MCPToolset(
        transport,
        id=BORROWED_FILESYSTEM_TOOLSET_ID,
        process_tool_call=audit_tool_call,
        tool_error_behavior="error",
    )
    return raw_toolset.filtered(borrowed_tool_is_read_only)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))

    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value

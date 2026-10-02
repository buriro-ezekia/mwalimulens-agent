"""Real smoke run for the official borrowed Filesystem MCP server."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from mwalimulens.agent.borrowed_filesystem import (
    BORROWED_FILESYSTEM_PACKAGE,
    BORROWED_FILESYSTEM_TOOL_ALLOWLIST,
    BORROWED_FILESYSTEM_TOOLSET_ID,
    BORROWED_FILESYSTEM_VERSION,
    BORROWED_FILESYSTEM_WRITE_TOOLS,
    DEFAULT_BORROWED_MCP_STDERR,
    DEFAULT_FILESYSTEM_ENTRYPOINT,
    DEFAULT_FILESYSTEM_PACKAGE_JSON,
    DEFAULT_REFERENCE_DIR,
    build_borrowed_filesystem_toolset,
    installed_filesystem_version,
)
from mwalimulens.mcp_server.server import PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore

DEFAULT_BORROWED_STATE_PATH = PROJECT_ROOT / "runtime" / "borrowed_mcp_state.json"
DEFAULT_BORROWED_REPORT_PATH = PROJECT_ROOT / "runtime" / "borrowed_mcp_run.json"
DEFAULT_REFERENCE_FILE = DEFAULT_REFERENCE_DIR / "math_fractions_reference.md"
REFERENCE_MARKER = "not learner evidence"


class _BorrowedFilesystemSmokeModel:
    def __init__(self, reference_file: Path) -> None:
        self.reference_file = reference_file.resolve()
        self.step = 0
        self.visible_tools: list[set[str]] = []
        self.tool_return = ""

    async def __call__(
        self,
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        self.visible_tools.append({tool.name for tool in info.function_tools})

        if self.step == 0:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "read_text_file",
                        {"path": str(self.reference_file)},
                    )
                ]
            )

        for message in reversed(messages):
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name == "read_text_file":
                    self.tool_return = str(part.content)
                    self.step += 1
                    return ModelResponse(
                        parts=[TextPart("Borrowed Filesystem MCP read completed.")]
                    )

        return ModelResponse(parts=[TextPart("Borrowed Filesystem MCP read result missing.")])


async def run_borrowed_mcp_smoke(
    *,
    reference_dir: Path = DEFAULT_REFERENCE_DIR,
    reference_file: Path = DEFAULT_REFERENCE_FILE,
    state_path: Path = DEFAULT_BORROWED_STATE_PATH,
    report_path: Path = DEFAULT_BORROWED_REPORT_PATH,
    entrypoint: Path = DEFAULT_FILESYSTEM_ENTRYPOINT,
    package_json_path: Path = DEFAULT_FILESYSTEM_PACKAGE_JSON,
    stderr_path: Path = DEFAULT_BORROWED_MCP_STDERR,
) -> dict[str, Any]:
    """Start the upstream server, execute one read, and persist inspectable evidence."""

    reference_dir = reference_dir.resolve()
    reference_file = reference_file.resolve()
    state_path = state_path.resolve()
    report_path = report_path.resolve()
    entrypoint = entrypoint.resolve()
    package_json_path = package_json_path.resolve()
    stderr_path = stderr_path.resolve()
    state_path.unlink(missing_ok=True)
    stderr_path.unlink(missing_ok=True)

    error: dict[str, str] | None = None
    model = _BorrowedFilesystemSmokeModel(reference_file)

    try:
        toolset = build_borrowed_filesystem_toolset(
            reference_dir=reference_dir,
            state_path=state_path,
            entrypoint=entrypoint,
            package_json_path=package_json_path,
            stderr_path=stderr_path,
        )
        agent = Agent(
            FunctionModel(model),
            instructions=(
                "Read the requested classroom reference through the borrowed "
                "official Filesystem MCP server."
            ),
            toolsets=[toolset],
        )
        async with agent:
            result = await agent.run("Read the MATH-FRACTIONS classroom reference.")
        final_output = str(result.output)
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        final_output = ""

    audited = [
        item
        for item in JsonStateStore(state_path).tool_calls()
        if item.get("toolset_id") == BORROWED_FILESYSTEM_TOOLSET_ID
    ]
    visible_tools = sorted(set().union(*model.visible_tools)) if model.visible_tools else []

    stderr_tail = _read_stderr_tail(stderr_path)
    installed_version = installed_filesystem_version(package_json_path)

    checks = {
        "official_package_pinned": BORROWED_FILESYSTEM_VERSION == "2026.8.31",
        "local_package_entrypoint": entrypoint.is_file(),
        "installed_package_version_matches": (
            installed_version == BORROWED_FILESYSTEM_VERSION
        ),
        "reference_directory_is_sandbox": reference_file.is_relative_to(reference_dir),
        "read_only_allowlist_visible": set(visible_tools)
        == BORROWED_FILESYSTEM_TOOL_ALLOWLIST,
        "write_tools_hidden": not set(visible_tools).intersection(
            BORROWED_FILESYSTEM_WRITE_TOOLS
        ),
        "read_text_file_succeeded": any(
            item.get("tool_name") == "read_text_file"
            and item.get("status") == "success"
            for item in audited
        ),
        "reference_content_returned": REFERENCE_MARKER in model.tool_return.lower(),
        "borrowed_call_audited": len(audited) == 1,
        "final_output_present": bool(final_output.strip()),
    }

    report = {
        "status": "pass" if error is None and all(checks.values()) else "fail",
        "borrowed_mcp": True,
        "server": "@modelcontextprotocol/server-filesystem",
        "package": BORROWED_FILESYSTEM_PACKAGE,
        "toolset_id": BORROWED_FILESYSTEM_TOOLSET_ID,
        "reference_dir": str(reference_dir),
        "reference_file": str(reference_file),
        "entrypoint": str(entrypoint),
        "installed_package_version": installed_version,
        "server_stderr_tail": stderr_tail,
        "visible_tools": visible_tools,
        "audited_tool_calls": audited,
        "checks": checks,
        "error": error,
        "final_output": final_output,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def _read_stderr_tail(path: Path, *, max_chars: int = 4000) -> str:
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace")
    return content[-max_chars:]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the official borrowed Filesystem MCP smoke check."
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=DEFAULT_REFERENCE_DIR,
    )
    parser.add_argument(
        "--reference-file",
        type=Path,
        default=DEFAULT_REFERENCE_FILE,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_BORROWED_REPORT_PATH,
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_borrowed_mcp_smoke(
            reference_dir=args.reference_dir,
            reference_file=args.reference_file,
            report_path=args.report,
        )
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

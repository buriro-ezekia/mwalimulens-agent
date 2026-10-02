"""Tests for the official borrowed Filesystem MCP integration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from mwalimulens.agent.borrowed_filesystem import (
    BORROWED_FILESYSTEM_PACKAGE,
    BORROWED_FILESYSTEM_TOOL_ALLOWLIST,
    BORROWED_FILESYSTEM_WRITE_TOOLS,
    DEFAULT_REFERENCE_DIR,
    borrowed_tool_is_read_only,
    build_borrowed_audit_callback,
    filesystem_stdio_spec,
)
from mwalimulens.agent.orchestrator import (
    AGENT_MCP_TOOL_ALLOWLIST,
    build_agent,
)
from mwalimulens.agent.promote_borrowed_mcp_evidence import (
    REQUIRED_BORROWED_CHECKS,
    promote_borrowed_mcp_report,
)
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_borrowed_filesystem_package_and_allowlist_are_pinned() -> None:
    assert BORROWED_FILESYSTEM_PACKAGE == (
        "@modelcontextprotocol/server-filesystem@2026.8.31"
    )
    assert BORROWED_FILESYSTEM_WRITE_TOOLS.isdisjoint(
        BORROWED_FILESYSTEM_TOOL_ALLOWLIST
    )


def test_filesystem_stdio_spec_supports_windows_and_posix(tmp_path) -> None:
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()

    command, args = filesystem_stdio_spec(reference_dir, windows=True)
    assert command == "cmd"
    assert args[:4] == ["/c", "npx", "-y", BORROWED_FILESYSTEM_PACKAGE]
    assert args[-1] == str(reference_dir.resolve())

    command, args = filesystem_stdio_spec(reference_dir, windows=False)
    assert command == "npx"
    assert args[:2] == ["-y", BORROWED_FILESYSTEM_PACKAGE]
    assert args[-1] == str(reference_dir.resolve())


def test_borrowed_filter_requires_allowlist_and_read_only_annotation() -> None:
    allowed = SimpleNamespace(
        name="read_text_file",
        metadata={"annotations": {"readOnlyHint": True}},
    )
    write_tool = SimpleNamespace(
        name="write_file",
        metadata={"annotations": {"readOnlyHint": False}},
    )
    unannotated = SimpleNamespace(
        name="read_text_file",
        metadata={"annotations": {}},
    )

    assert borrowed_tool_is_read_only(None, allowed) is True
    assert borrowed_tool_is_read_only(None, write_tool) is False
    assert borrowed_tool_is_read_only(None, unannotated) is False


def test_reference_fixture_is_explicitly_not_learner_evidence() -> None:
    content = (DEFAULT_REFERENCE_DIR / "math_fractions_reference.md").read_text(
        encoding="utf-8"
    ).lower()

    assert "not learner evidence" in content
    assert "counter-evidence" in content
    assert "teacher remains responsible" in content


@pytest.mark.anyio
async def test_borrowed_audit_wrapper_records_success(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    callback = build_borrowed_audit_callback(state_path)

    async def call_tool(name, args):
        assert name == "read_text_file"
        assert args == {"path": "reference.md"}
        return {"content": "reference"}

    result = await callback(
        None,
        call_tool,
        "read_text_file",
        {"path": "reference.md"},
    )

    assert result == {"content": "reference"}
    events = JsonStateStore(state_path).tool_calls()
    assert len(events) == 1
    assert events[0]["source"] == "borrowed_mcp"
    assert events[0]["status"] == "success"
    assert events[0]["tool_name"] == "read_text_file"


@pytest.mark.anyio
async def test_borrowed_audit_wrapper_records_error(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    callback = build_borrowed_audit_callback(state_path)

    async def call_tool(_name, _args):
        raise RuntimeError("borrowed read failed")

    with pytest.raises(RuntimeError, match="borrowed read failed"):
        await callback(
            None,
            call_tool,
            "read_text_file",
            {"path": "reference.md"},
        )

    events = JsonStateStore(state_path).tool_calls()
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"]["type"] == "RuntimeError"


@pytest.mark.anyio
async def test_agent_can_compose_custom_and_additional_toolsets(tmp_path) -> None:
    extra = FunctionToolset()

    @extra.tool_plain
    def reference_stub(path: str) -> str:
        return path

    model = TestModel(call_tools=[], custom_output_text="done")
    agent = build_agent(
        model,
        data_dir=FIXTURE_DIR,
        state_path=tmp_path / "state.json",
        additional_toolsets=[extra],
    )

    result = await agent.run("Inspect model-visible tools.")

    assert result.output == "done"
    assert model.last_model_request_parameters is not None
    visible = {
        tool.name for tool in model.last_model_request_parameters.function_tools
    }
    assert AGENT_MCP_TOOL_ALLOWLIST.issubset(visible)
    assert "reference_stub" in visible
    assert "record_teacher_review" not in visible


def test_passing_borrowed_report_can_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    destination = tmp_path / "evidence.json"
    report = {
        "status": "pass",
        "borrowed_mcp": True,
        "server": "@modelcontextprotocol/server-filesystem",
        "package": BORROWED_FILESYSTEM_PACKAGE,
        "checks": {name: True for name in REQUIRED_BORROWED_CHECKS},
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    promoted = promote_borrowed_mcp_report(
        source=source,
        destination=destination,
    )

    assert promoted == report
    assert destination.is_file()


def test_failed_borrowed_report_cannot_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    report = {
        "status": "fail",
        "borrowed_mcp": True,
        "server": "@modelcontextprotocol/server-filesystem",
        "checks": {name: False for name in REQUIRED_BORROWED_CHECKS},
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="status must be pass"):
        promote_borrowed_mcp_report(
            source=source,
            destination=tmp_path / "evidence.json",
        )

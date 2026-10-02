"""PydanticAI orchestrator with an MCP-enforced human boundary."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, DEFAULT_STATE_PATH, PROJECT_ROOT

AGENT_MCP_TOOL_ALLOWLIST = frozenset(
    {
        "get_learner_timeline",
        "get_competency_evidence",
        "flag_pattern_for_review",
    }
)

AGENT_INSTRUCTIONS = """
You are MwalimuLens, an evidence-grounded longitudinal learning assistant for teachers.

Use MCP evidence tools before making any learner-pattern claim. Every candidate pattern must be
grounded in concrete evidence IDs. Actively look for counter-evidence and state uncertainty.
A single score is not enough to establish a persistent strength or weakness. If longitudinal
history is insufficient, say so rather than inventing a durable trait.

Never rank a learner against classmates. Never assign a permanent learner label, career, subject
pathway or track. You may submit a defensible candidate with flag_pattern_for_review, but the
teacher decides whether to approve, edit or reject it. You have no authority to perform the human
review or to create a learner-profile update.
""".strip()


def build_agent_mcp_toolset(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
):
    """Build the MCP toolset exposed to the agent, filtered before model visibility."""

    environment = dict(os.environ)
    environment["MWALIMULENS_DATA_DIR"] = str(data_dir.resolve())
    environment["MWALIMULENS_STATE_PATH"] = str(state_path.resolve())

    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "mwalimulens.mcp_server.server"],
        env=environment,
        cwd=str(PROJECT_ROOT),
        keep_alive=False,
    )
    raw_toolset = MCPToolset(
        transport,
        id="mwalimulens-education-mcp",
        tool_error_behavior="error",
    )
    return raw_toolset.filtered(
        lambda _ctx, tool_def: tool_def.name in AGENT_MCP_TOOL_ALLOWLIST
    )


def build_agent(
    model,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
) -> Agent:
    """Build a model-independent MwalimuLens agent with the strict MCP allowlist."""

    return Agent(
        model,
        instructions=AGENT_INSTRUCTIONS,
        toolsets=[
            build_agent_mcp_toolset(
                data_dir=data_dir,
                state_path=state_path,
            )
        ],
    )

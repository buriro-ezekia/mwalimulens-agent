"""PydanticAI orchestration for MwalimuLens."""

from mwalimulens.agent.ollama import OllamaSettings, build_ollama_agent, build_ollama_model
from mwalimulens.agent.orchestrator import (
    AGENT_INSTRUCTIONS,
    AGENT_MCP_TOOL_ALLOWLIST,
    EDUCATION_MCP_CLIENT_MODE,
    build_agent,
    build_agent_mcp_client,
    build_agent_mcp_toolset,
)

__all__ = [
    "AGENT_INSTRUCTIONS",
    "EDUCATION_MCP_CLIENT_MODE",
    "OllamaSettings",
    "build_ollama_agent",
    "build_ollama_model",
    "AGENT_MCP_TOOL_ALLOWLIST",
    "build_agent",
    "build_agent_mcp_client",
    "build_agent_mcp_toolset",
]

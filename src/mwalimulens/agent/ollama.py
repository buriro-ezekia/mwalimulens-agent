"""Local Ollama/Qwen model configuration for MwalimuLens."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from mwalimulens.agent.orchestrator import build_agent
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, DEFAULT_STATE_PATH

DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    """Configuration for a local open-weights Ollama model."""

    model_name: str = DEFAULT_OLLAMA_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("base_url must be a non-empty string")

        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        if parsed.path.rstrip("/") != "/v1":
            raise ValueError("base_url must target Ollama's OpenAI-compatible /v1 endpoint")

    @classmethod
    def from_env(cls) -> OllamaSettings:
        """Load local model settings from the MwalimuLens environment."""

        return cls(
            model_name=os.environ.get(
                "MWALIMULENS_OLLAMA_MODEL",
                DEFAULT_OLLAMA_MODEL,
            ),
            base_url=os.environ.get(
                "MWALIMULENS_OLLAMA_BASE_URL",
                DEFAULT_OLLAMA_BASE_URL,
            ),
        )


def build_ollama_model(settings: OllamaSettings | None = None) -> OllamaModel:
    """Build the local Ollama model without making a network request."""

    settings = settings or OllamaSettings.from_env()
    provider = OllamaProvider(base_url=settings.base_url)
    return OllamaModel(settings.model_name, provider=provider)


def build_ollama_agent(
    *,
    settings: OllamaSettings | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
    additional_toolsets: Sequence[Any] = (),
):
    """Build the safe MwalimuLens agent backed by local Qwen/Ollama."""

    return build_agent(
        build_ollama_model(settings),
        data_dir=data_dir,
        state_path=state_path,
        additional_toolsets=additional_toolsets,
    )

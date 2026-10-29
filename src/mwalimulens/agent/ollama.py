"""Local Ollama/Qwen model configuration for MwalimuLens."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic_ai.messages import RetryPromptPart, ToolCallPart
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
    keep_alive: str | None = None

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
        if self.keep_alive is not None:
            match = re.fullmatch(r"([1-9][0-9]*)([smh])", self.keep_alive)
            if match is None:
                raise ValueError("keep_alive must be a positive duration such as 30m")
            count, unit = match.groups()
            if int(count) * {"s": 1, "m": 60, "h": 3600}[unit] > 3600:
                raise ValueError("keep_alive must not exceed one hour")
            if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Model preloading is only permitted on loopback")

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
            keep_alive=os.environ.get("MWALIMULENS_OLLAMA_KEEP_ALIVE") or None,
        )


def prewarm_ollama(settings: OllamaSettings) -> dict[str, Any]:
    """Optionally load a local model using Ollama's native keep-alive API."""

    if settings.keep_alive is None:
        return {"attempted": False, "status": "disabled", "seconds": None}
    parsed = urlparse(settings.base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Model preloading is only permitted on loopback")
    endpoint = parsed._replace(path="/api/generate", params="", query="", fragment="")
    data = json.dumps({
        "model": settings.model_name,
        "prompt": "",
        "stream": False,
        "keep_alive": settings.keep_alive,
    }).encode("utf-8")
    request = Request(
        endpoint.geturl(), data=data, headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = perf_counter()
    with urlopen(request, timeout=90) as response:
        payload = json.load(response)
    if payload.get("done") is not True or payload.get("model") != settings.model_name:
        raise RuntimeError("Local Ollama preloading did not confirm the requested model")
    return {
        "attempted": True,
        "status": "pass",
        "seconds": round(perf_counter() - started, 3),
        "requested_keep_alive": settings.keep_alive,
    }


def _token_count(usage: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(usage, name, None)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


class TimedOllamaModel(OllamaModel):
    """Observe per-request wall time and provider usage without storing prompts."""

    def __init__(
        self, name: str, *, provider: OllamaProvider, records: list,
        audit_snapshot: Callable[[], Sequence[str]] | None = None,
        trace_path: Path | None = None,
    ) -> None:
        super().__init__(name, provider=provider)
        self._records = records
        self._audit_snapshot = audit_snapshot
        self._trace_path = trace_path

    def _trace(self, event: dict[str, Any]) -> None:
        """Append non-sensitive request metadata before a subprocess can time out."""

        if self._trace_path is None:
            return
        self._trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self._trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        index = len(self._records) + 1
        started = perf_counter()
        messages = args[0] if args else kwargs.get("messages", ())
        record: dict[str, Any] = {
            "request": index,
            # Counts feedback in this request's history, not new service errors.
            "retry_feedback_count": sum(
                isinstance(part, RetryPromptPart)
                for message in messages
                for part in getattr(message, "parts", ())
            ),
        }
        if self._audit_snapshot is not None:
            record["audited_tools_before"] = list(self._audit_snapshot())
        self._trace({
            "event": "request_started",
            "request": index,
            "retry_feedback_count": record["retry_feedback_count"],
            "audited_tools_before": record.get("audited_tools_before", []),
        })
        try:
            response = await super().request(*args, **kwargs)
            usage = getattr(response, "usage", None)
            record.update({
                "status": "pass",
                "input_tokens": _token_count(usage, "input_tokens", "request_tokens"),
                "output_tokens": _token_count(usage, "output_tokens", "response_tokens"),
                "total_tokens": _token_count(usage, "total_tokens"),
                "requested_tool_names": [
                    part.tool_name for part in getattr(response, "parts", ())
                    if isinstance(part, ToolCallPart)
                ],
            })
            return response
        except Exception as exc:
            record.update({"status": "error", "error_type": type(exc).__name__})
            raise
        finally:
            record["seconds"] = round(perf_counter() - started, 3)
            if self._audit_snapshot is not None:
                record["audited_tools_after"] = list(self._audit_snapshot())
            if "status" not in record:
                record["status"] = "interrupted"
            self._records.append(record)
            self._trace({"event": "request_finished", **record})


def build_ollama_model(
    settings: OllamaSettings | None = None, *, records: list | None = None,
    audit_snapshot: Callable[[], Sequence[str]] | None = None,
    trace_path: Path | None = None,
) -> OllamaModel:
    """Build the local Ollama model without making a network request."""

    settings = settings or OllamaSettings.from_env()
    provider = OllamaProvider(base_url=settings.base_url)
    if records is not None:
        return TimedOllamaModel(
            settings.model_name, provider=provider, records=records,
            audit_snapshot=audit_snapshot, trace_path=trace_path,
        )
    return OllamaModel(settings.model_name, provider=provider)


def build_ollama_agent(
    *,
    settings: OllamaSettings | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
    additional_toolsets: Sequence[Any] = (),
    records: list | None = None,
    audit_snapshot: Callable[[], Sequence[str]] | None = None,
    trace_path: Path | None = None,
    tool_error_behavior: str = "error",
    allow_candidate_action: bool = True,
):
    """Build the safe MwalimuLens agent backed by local Qwen/Ollama."""

    return build_agent(
        build_ollama_model(
            settings, records=records, audit_snapshot=audit_snapshot,
            trace_path=trace_path,
        ),
        data_dir=data_dir,
        state_path=state_path,
        additional_toolsets=additional_toolsets,
        tool_error_behavior=tool_error_behavior,
        allow_candidate_action=allow_candidate_action,
    )

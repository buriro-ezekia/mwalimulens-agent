"""Native Ollama JSON-schema generation; no model-accessible action tools."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx


class OllamaJsonGenerator:
    """Generate a decision under a shared absolute deadline and request budget."""

    def __init__(
        self, *, model: str, base_url: str, deadline: float, request_limit: int,
        records: list[dict[str, Any]], observe: Callable[[dict[str, Any]], None],
        keep_alive: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "localhost", "127.0.0.1", "::1"
        } or parsed.username or parsed.password:
            raise ValueError("Structured review requires a credential-free loopback Ollama URL")
        if (
            not isinstance(request_limit, int) or isinstance(request_limit, bool)
            or request_limit < 1
        ):
            raise ValueError("request_limit must be positive")
        self.endpoint = parsed._replace(
            path="/api/chat", params="", query="", fragment=""
        ).geturl()
        self.model = model
        self.deadline = deadline
        self.request_limit = request_limit
        self.records = records
        self.observe = observe
        self.keep_alive = keep_alive
        self.transport = transport

    async def __call__(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        if len(self.records) >= self.request_limit:
            raise RuntimeError("Shared structured request budget exhausted")
        if asyncio.get_running_loop().time() >= self.deadline:
            raise TimeoutError("Shared structured deadline exceeded")
        record: dict[str, Any] = {
            "request": len(self.records) + 1, "status": "running",
            "mode": "native_json_schema", "requested_tool_names": [],
        }
        self.records.append(record)
        self.observe({"event": "request_started", **record})
        start = perf_counter()
        payload: dict[str, Any] = {
            "model": self.model, "messages": messages, "stream": False,
            "format": schema, "options": {"temperature": 0, "num_predict": 1024},
        }
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        try:
            async with asyncio.timeout_at(self.deadline):
                async with httpx.AsyncClient(
                    timeout=None, transport=self.transport, trust_env=False,
                ) as client:
                    response = await client.post(self.endpoint, json=payload)
                    response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("done") is not True:
                raise ValueError("Ollama did not confirm a completed response")
            if data.get("done_reason") == "length":
                raise ValueError("Ollama decision was truncated; no submission is permitted")
            message = data.get("message")
            if not isinstance(message, dict) or message.get("tool_calls"):
                raise ValueError("A structured decision, not an action tool call, is required")
            text = message.get("content")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Ollama returned no structured decision")
            record.update(status="returned", input_tokens=data.get("prompt_eval_count"),
                          output_tokens=data.get("eval_count"))
            # Only non-sensitive provider metrics enter the trace.
            for name in ("load_duration", "prompt_eval_duration", "eval_duration"):
                value = data.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    record[name + "_seconds"] = value / 1e9
            return text
        except asyncio.CancelledError:
            record["status"] = "interrupted"
            raise
        except Exception as exc:
            record.update(status="error", error_type=type(exc).__name__)
            raise
        finally:
            record["seconds"] = round(perf_counter() - start, 3)
            self.observe({"event": "request_finished", **record})

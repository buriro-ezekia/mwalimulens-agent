"""Per-review reuse of an immutable, fully sourced MCP evidence snapshot."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelRetry
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.toolsets.wrapper import WrapperToolset


@dataclass
class CompetencyReviewToolset(WrapperToolset):
    target: tuple[str, str]
    events: list[dict[str, Any]] = field(default_factory=list)
    snapshots: dict[str, Any] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    session: dict[str, int] = field(default_factory=lambda: {"depth": 0})

    async def __aenter__(self):
        if self.session["depth"] == 0:
            self.snapshots.clear()
        await super().__aenter__()
        self.session["depth"] += 1
        return self

    async def __aexit__(self, *args):
        try:
            return await super().__aexit__(*args)
        finally:
            self.session["depth"] -= 1
            if self.session["depth"] == 0:
                self.snapshots.clear()

    def _snapshot_accessible(self, ctx) -> bool:
        if (
            "result" not in self.snapshots
            or self.snapshots["target"] != self.target
            or self.snapshots["source"] is not self.wrapped
        ):
            return False
        # Parallel calls in one response are resolved before tool returns enter history.
        if (
            getattr(ctx, "run_id", None) is not None
            and self.snapshots["run_id"] == ctx.run_id
            and self.snapshots["run_step"] == ctx.run_step
        ):
            return True
        return any(
            isinstance(part, ToolReturnPart)
            and part.tool_name == "get_competency_evidence"
            and part.tool_call_id == self.snapshots["tool_call_id"]
            and part.outcome == "success"
            and part.content == self.snapshots["result"]
            for message in getattr(ctx, "messages", [])
            for part in message.parts
        )

    async def get_tools(self, ctx):
        tools = await super().get_tools(ctx)
        return {name: tool for name, tool in tools.items() if name != "get_learner_timeline"}

    async def call_tool(self, name, tool_args, ctx, tool):
        if name != "get_competency_evidence":
            return await super().call_tool(name, tool_args, ctx, tool)
        event = {"tool_name": name, "inputs": dict(tool_args), "tool_call_id": ctx.tool_call_id}
        self.events.append(event)
        if tool_args != {"learner_id": self.target[0], "competency_code": self.target[1]}:
            event["status"] = "rejected_target"
            raise ModelRetry("Retrieve only the learner and competency specified for this review.")
        # Serialize duplicate calls in the same model response as well as across stages.
        async with self.lock:
            if self._snapshot_accessible(ctx):
                event["status"] = "snapshot_reused"
                return {
                    "snapshot_reused": True,
                    "original_tool_call_id": self.snapshots["tool_call_id"],
                    "learner_id": self.target[0], "competency_code": self.target[1],
                    "note": "Use the complete evidence and provenance in the original tool result "
                            "already in this conversation. No new retrieval was performed.",
                }
            event["status"] = "started"
            try:
                result = await super().call_tool(name, tool_args, ctx, tool)
            except BaseException:
                event["status"] = "unsuccessful"
                raise
            # Keep the original MCP result intact; never condense evidence or manufacture fields.
            self.snapshots.update(
                result=deepcopy(result), tool_call_id=ctx.tool_call_id, target=self.target,
                source=self.wrapped, run_id=getattr(ctx, "run_id", None),
                run_step=getattr(ctx, "run_step", None),
            )
            event["status"] = "retrieved"
            return result

"""Small execution-control and durable JSON primitives."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionLimits:
    request_limit: int = 6
    deadline_seconds: float = 540

    def __post_init__(self):
        if isinstance(self.request_limit, bool) or not isinstance(self.request_limit, int):
            raise ValueError("request_limit must be a positive integer")
        if self.request_limit < 1:
            raise ValueError("request_limit must be a positive integer")
        if not math.isfinite(self.deadline_seconds) or self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be finite and positive")


def atomic_json(path: Path, payload: Any) -> None:
    """Replace a checkpoint only after a complete JSON document is flushed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

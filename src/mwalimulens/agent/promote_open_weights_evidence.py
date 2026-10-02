"""Promote a successful local open-weights run into repository evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mwalimulens.agent.open_weights_run import DEFAULT_OPEN_WEIGHTS_REPORT_PATH
from mwalimulens.mcp_server.server import PROJECT_ROOT

DEFAULT_COMMITTED_EVIDENCE_PATH = PROJECT_ROOT / "evidence" / "open_weights_run.json"


def promote_open_weights_report(
    *,
    source: Path = DEFAULT_OPEN_WEIGHTS_REPORT_PATH,
    destination: Path = DEFAULT_COMMITTED_EVIDENCE_PATH,
) -> dict[str, Any]:
    """Validate and copy only a passing run report into judge-facing evidence."""

    report = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("open-weights report must be a JSON object")

    checks = report.get("checks")
    if report.get("status") != "pass":
        raise ValueError("open-weights report status must be pass before promotion")
    if report.get("provider") != "ollama" or report.get("open_weights") is not True:
        raise ValueError("open-weights report must identify a local Ollama open-weights run")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        raise ValueError("all open-weights evidence checks must pass before promotion")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote a passing local Qwen/Ollama run into repository evidence."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_OPEN_WEIGHTS_REPORT_PATH,
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_COMMITTED_EVIDENCE_PATH,
    )
    args = parser.parse_args()

    try:
        report = promote_open_weights_report(
            source=args.source,
            destination=args.destination,
        )
    except Exception as exc:
        print(f"Evidence promotion blocked: {type(exc).__name__}: {exc}")
        return 1

    print(
        "Promoted open-weights evidence: "
        f"{report['model']} -> {args.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

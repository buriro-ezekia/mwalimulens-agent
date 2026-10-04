"""Promote a passing consolidated challenge run into repository evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mwalimulens.challenge_run import (
    DEFAULT_CHALLENGE_MODEL,
    DEFAULT_CHALLENGE_REPORT_PATH,
)
from mwalimulens.mcp_server.server import PROJECT_ROOT

DEFAULT_CHALLENGE_EVIDENCE_PATH = PROJECT_ROOT / "evidence" / "challenge_run.json"
REQUIRED_CHALLENGE_CHECKS = frozenset(
    {
        "ollama_preflight_passed",
        "open_weights_task_passed",
        "borrowed_mcp_smoke_passed",
        "evaluation_suite_passed",
        "human_gate_preserved",
    }
)


def promote_challenge_report(
    *,
    source: Path = DEFAULT_CHALLENGE_REPORT_PATH,
    destination: Path = DEFAULT_CHALLENGE_EVIDENCE_PATH,
) -> dict[str, Any]:
    """Promote only a complete passing one-command challenge report."""

    report = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("challenge report must be a JSON object")
    if report.get("status") != "pass":
        raise ValueError("challenge report status must be pass before promotion")
    if report.get("model") != DEFAULT_CHALLENGE_MODEL:
        raise ValueError(
            f"challenge evidence must use the default model: {DEFAULT_CHALLENGE_MODEL}"
        )

    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("challenge report checks must be a JSON object")

    missing = REQUIRED_CHALLENGE_CHECKS.difference(checks)
    if missing:
        raise ValueError(f"challenge report is missing required checks: {sorted(missing)}")
    if not all(checks[name] is True for name in REQUIRED_CHALLENGE_CHECKS):
        raise ValueError("all required challenge checks must pass before promotion")

    components = report.get("components")
    if not isinstance(components, dict):
        raise ValueError("challenge report components must be a JSON object")
    required_components = {"open_weights", "borrowed_mcp", "evaluations"}
    if not required_components.issubset(components):
        raise ValueError("challenge report is missing required component summaries")
    if not all(components[name].get("status") == "pass" for name in required_components):
        raise ValueError("every required challenge component must have status pass")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote passing challenge-run evidence.")
    parser.add_argument("--source", type=Path, default=DEFAULT_CHALLENGE_REPORT_PATH)
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_CHALLENGE_EVIDENCE_PATH,
    )
    args = parser.parse_args()

    try:
        report = promote_challenge_report(
            source=args.source,
            destination=args.destination,
        )
    except Exception as exc:
        print(f"Challenge evidence promotion blocked: {type(exc).__name__}: {exc}")
        return 1

    print(
        "Promoted one-command challenge evidence: "
        f"{report['model']} -> {args.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

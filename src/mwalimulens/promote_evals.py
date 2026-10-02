"""Promote a passing MwalimuLens evaluation report into repository evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mwalimulens.evals import DEFAULT_EVAL_REPORT_PATH
from mwalimulens.mcp_server.server import PROJECT_ROOT

DEFAULT_EVAL_EVIDENCE_PATH = PROJECT_ROOT / "evidence" / "evals_run.json"


def promote_eval_report(
    *,
    source: Path = DEFAULT_EVAL_REPORT_PATH,
    destination: Path = DEFAULT_EVAL_EVIDENCE_PATH,
) -> dict[str, Any]:
    """Promote only a complete suite with passing current regressions and preserved failures."""

    report = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("evaluation report must be a JSON object")
    if report.get("status") != "pass":
        raise ValueError("evaluation report status must be pass before promotion")

    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("evaluation report summary must be a JSON object")
    if summary.get("total_cases", 0) < 8:
        raise ValueError("evaluation report must contain at least 8 cases")
    if summary.get("current_fail") != 0:
        raise ValueError("all current regression cases must pass")
    if summary.get("historical_fail_preserved", 0) < 1:
        raise ValueError("at least one genuine historical model failure must remain preserved")

    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != summary["total_cases"]:
        raise ValueError("evaluation report cases do not match summary total")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote passing evaluation evidence.")
    parser.add_argument("--source", type=Path, default=DEFAULT_EVAL_REPORT_PATH)
    parser.add_argument("--destination", type=Path, default=DEFAULT_EVAL_EVIDENCE_PATH)
    args = parser.parse_args()

    try:
        report = promote_eval_report(source=args.source, destination=args.destination)
    except Exception as exc:
        print(f"Evaluation evidence promotion blocked: {type(exc).__name__}: {exc}")
        return 1

    print(
        "Promoted evaluation evidence: "
        f"{report['summary']['current_pass']} current PASS / "
        f"{report['summary']['historical_fail_preserved']} historical FAIL -> "
        f"{args.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Promote a passing borrowed-MCP smoke report into repository evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mwalimulens.agent.borrowed_mcp_run import DEFAULT_BORROWED_REPORT_PATH
from mwalimulens.mcp_server.server import PROJECT_ROOT

DEFAULT_BORROWED_EVIDENCE_PATH = PROJECT_ROOT / "evidence" / "borrowed_mcp_run.json"

REQUIRED_BORROWED_CHECKS = frozenset(
    {
        "official_package_pinned",
        "legacy_handshake_mode",
        "reference_directory_is_sandbox",
        "read_only_allowlist_visible",
        "write_tools_hidden",
        "read_text_file_succeeded",
        "reference_content_returned",
        "borrowed_call_audited",
        "final_output_present",
    }
)


def promote_borrowed_mcp_report(
    *,
    source: Path = DEFAULT_BORROWED_REPORT_PATH,
    destination: Path = DEFAULT_BORROWED_EVIDENCE_PATH,
) -> dict[str, Any]:
    """Copy only a fully passing official borrowed-MCP report into evidence."""

    report = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("borrowed MCP report must be a JSON object")
    if report.get("status") != "pass":
        raise ValueError("borrowed MCP report status must be pass before promotion")
    if report.get("borrowed_mcp") is not True:
        raise ValueError("report must identify a borrowed MCP run")
    if report.get("server") != "@modelcontextprotocol/server-filesystem":
        raise ValueError("report must identify the official Filesystem MCP server")

    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("borrowed MCP report checks must be a JSON object")

    missing = REQUIRED_BORROWED_CHECKS.difference(checks)
    if missing:
        raise ValueError(f"borrowed MCP report is missing required checks: {sorted(missing)}")
    if not all(checks[name] is True for name in REQUIRED_BORROWED_CHECKS):
        raise ValueError("all required borrowed MCP checks must pass before promotion")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote passing borrowed Filesystem MCP evidence."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_BORROWED_REPORT_PATH)
    parser.add_argument("--destination", type=Path, default=DEFAULT_BORROWED_EVIDENCE_PATH)
    args = parser.parse_args()

    try:
        report = promote_borrowed_mcp_report(
            source=args.source,
            destination=args.destination,
        )
    except Exception as exc:
        print(f"Borrowed MCP evidence promotion blocked: {type(exc).__name__}: {exc}")
        return 1

    print(
        "Promoted borrowed MCP evidence: "
        f"{report['package']} -> {args.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

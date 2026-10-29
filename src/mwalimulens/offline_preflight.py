"""Offline-stage readiness checks without modifying challenge submission evidence."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "runtime" / "offline_preflight"


def check_prerequisites(root: Path = ROOT, *, which=shutil.which) -> dict[str, bool]:
    """Check only local files and executables; do not download dependencies."""
    node = which("node")
    checks = {
        "python_3_11_or_newer": sys.version_info >= (3, 11),
        "node_available": node is not None,
        "synthetic_fixtures": (
            (root / "data" / "synthetic" / "learners.json").is_file()
            and (root / "data" / "synthetic" / "learning_evidence.json").is_file()
        ),
        "borrowed_filesystem_mcp_installed": (
            root / "node_modules" / "@modelcontextprotocol" /
            "server-filesystem" / "dist" / "index.js"
        ).is_file(),
    }
    if node is not None:
        try:
            proc = subprocess.run([node, "--version"], capture_output=True,
                                  text=True, timeout=5, check=False)
            major = int(proc.stdout.strip().lstrip("v").split(".")[0])
            checks["node_20_or_newer"] = proc.returncode == 0 and major >= 20
        except (OSError, ValueError, subprocess.TimeoutExpired):
            checks["node_20_or_newer"] = False
    else:
        checks["node_20_or_newer"] = False
    return checks


def inspect_mcp_case(case: Any) -> dict[str, bool]:
    """Verify genuine fast MCP activity and the untouched human gate."""
    calls = list(case.state.tool_calls())
    successful = {
        x.get("tool_name") for x in calls if x.get("status") == "success"
    }
    return {
        "education_mcp_retrieval": "get_competency_evidence" in successful,
        "borrowed_filesystem_read": "read_text_file" in successful,
        "candidate_action": "flag_pattern_for_review" in successful,
        "pending_candidate": len(case.state.pending_reviews()) == 1,
        "no_teacher_decision": len(case.state.teacher_reviews()) == 0,
        "no_profile_update": len(case.state.profile_updates()) == 0,
        "real_mcp_report_passed": bool(case.report and case.report.get("status") == "pass"),
    }


def run_preflight(*, output_root: Path = DEFAULT_OUTPUT,
                  run_mcp: bool = False,
                  check_model: bool = False) -> dict[str, Any]:
    """Produce a local JSON report, explicitly distinguishing skipped gates."""
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="preflight-", dir=output_root))
    checks = check_prerequisites()
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "prerequisites": checks,
        "mcp": {"status": "not_run"},
        "model": {"status": "not_checked"},
        "manual_offline_connectivity_verified": False,
        "note": "Only a user-disconnected rehearsal can verify offline connectivity.",
    }
    if check_model:
        try:
            from mwalimulens.agent.ollama import OllamaSettings
            from mwalimulens.challenge_run import preflight_ollama
            report["model"] = preflight_ollama(OllamaSettings.from_env())
        except (OSError, RuntimeError, ValueError) as exc:
            report["model"] = {"status": "fail", "error": type(exc).__name__}
    if run_mcp:
        try:
            from mwalimulens.teacher_portal import create_case
            case = create_case(run_dir, "mcp")
            observed = inspect_mcp_case(case)
            report["mcp"] = {
                "status": "pass" if all(observed.values()) else "fail",
                "checks": observed,
                "run_directory": str(case.run_dir),
            }
        except (OSError, RuntimeError, ValueError) as exc:
            report["mcp"] = {"status": "fail", "error": type(exc).__name__}
    report["status"] = (
        "automated_pass" if all(checks.values())
        and report["mcp"]["status"] == "pass"
        and (not check_model or report["model"]["status"] == "pass")
        else "incomplete_or_failed"
    )
    path = run_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"report_path": str(path), **report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-mcp", action="store_true")
    parser.add_argument("--check-model", action="store_true")
    args = parser.parse_args(argv)
    result = run_preflight(output_root=args.output_dir,
                           run_mcp=args.run_mcp, check_model=args.check_model)
    print(f"product preflight: {result['status']}")
    print(f"Local report: {result['report_path']}")
    print("Offline connectivity still requires a manual disconnected rehearsal.")
    return 0 if result["status"] == "automated_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

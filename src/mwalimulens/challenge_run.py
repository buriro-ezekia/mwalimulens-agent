"""Consolidated judge-facing MwalimuLens challenge run."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from mwalimulens.agent.borrowed_mcp_run import run_borrowed_mcp_smoke
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.open_weights_run import run_open_weights_task
from mwalimulens.evals import run_evaluations
from mwalimulens.mcp_server.server import PROJECT_ROOT

DEFAULT_CHALLENGE_MODEL = "qwen2.5:3b"
DEFAULT_CHALLENGE_REPORT_PATH = PROJECT_ROOT / "runtime" / "challenge_run.json"
DEFAULT_CHALLENGE_OPEN_WEIGHTS_REPORT = (
    PROJECT_ROOT / "runtime" / "challenge_open_weights_run.json"
)
DEFAULT_CHALLENGE_OPEN_WEIGHTS_STATE = (
    PROJECT_ROOT / "runtime" / "challenge_open_weights_state.json"
)
DEFAULT_CHALLENGE_BORROWED_REPORT = (
    PROJECT_ROOT / "runtime" / "challenge_borrowed_mcp_run.json"
)
DEFAULT_CHALLENGE_BORROWED_STATE = (
    PROJECT_ROOT / "runtime" / "challenge_borrowed_mcp_state.json"
)
DEFAULT_CHALLENGE_BORROWED_STDERR = (
    PROJECT_ROOT / "runtime" / "challenge_borrowed_mcp_stderr.log"
)
DEFAULT_CHALLENGE_EVAL_REPORT = PROJECT_ROOT / "runtime" / "challenge_evals_run.json"


def ollama_tags_url(base_url: str) -> str:
    """Return the local Ollama tags endpoint for an OpenAI-compatible /v1 base URL."""

    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/api/tags"


def preflight_ollama(
    settings: OllamaSettings,
    *,
    fetch_json: Callable[[str, float], dict[str, Any]] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Verify a local Ollama endpoint and the requested open-weights model."""

    fetch_json = fetch_json or _fetch_json
    hostname = (urlparse(settings.base_url).hostname or "").lower()
    local_endpoint = hostname in {"localhost", "127.0.0.1", "::1"}
    tags_url = ollama_tags_url(settings.base_url)

    if not local_endpoint:
        return {
            "status": "fail",
            "base_url": settings.base_url,
            "model": settings.model_name,
            "models_found": [],
            "error": "Ollama base URL must resolve to the local machine.",
            "remediation": "Use the local Ollama endpoint, normally http://localhost:11434/v1.",
        }

    try:
        payload = fetch_json(tags_url, timeout)
    except Exception as exc:
        return {
            "status": "fail",
            "base_url": settings.base_url,
            "model": settings.model_name,
            "models_found": [],
            "error": f"{type(exc).__name__}: {exc}",
            "remediation": "Start Ollama locally, then rerun the same challenge command.",
        }

    models = payload.get("models", [])
    if not isinstance(models, list):
        return {
            "status": "fail",
            "base_url": settings.base_url,
            "model": settings.model_name,
            "models_found": [],
            "error": "Ollama tags response field 'models' must be a list.",
            "remediation": "Restart or update the local Ollama service, then rerun.",
        }

    names = sorted(
        {
            candidate
            for item in models
            if isinstance(item, dict)
            for candidate in (item.get("name"), item.get("model"))
            if isinstance(candidate, str) and candidate.strip()
        }
    )
    model_present = settings.model_name in names
    return {
        "status": "pass" if model_present else "fail",
        "base_url": settings.base_url,
        "model": settings.model_name,
        "models_found": names,
        "error": (
            None
            if model_present
            else f"required model is not installed: {settings.model_name}"
        ),
        "remediation": (
            None
            if model_present
            else f"Run ollama pull {settings.model_name} once, then rerun this command."
        ),
    }


async def run_challenge(
    *,
    settings: OllamaSettings,
    report_path: Path = DEFAULT_CHALLENGE_REPORT_PATH,
) -> dict[str, Any]:
    """Run all judge-facing challenge paths and persist one consolidated report."""

    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    started_at = datetime.now(UTC)
    preflight = preflight_ollama(settings)

    if preflight["status"] == "pass":
        open_weights = await run_open_weights_task(
            settings=settings,
            state_path=DEFAULT_CHALLENGE_OPEN_WEIGHTS_STATE,
            report_path=DEFAULT_CHALLENGE_OPEN_WEIGHTS_REPORT,
        )
    else:
        open_weights = _skipped_component("Ollama preflight failed.")

    borrowed_mcp = await run_borrowed_mcp_smoke(
        state_path=DEFAULT_CHALLENGE_BORROWED_STATE,
        report_path=DEFAULT_CHALLENGE_BORROWED_REPORT,
        stderr_path=DEFAULT_CHALLENGE_BORROWED_STDERR,
    )

    try:
        evals = run_evaluations(report_path=DEFAULT_CHALLENGE_EVAL_REPORT)
    except Exception as exc:
        evals = {
            "status": "fail",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

    finished_at = datetime.now(UTC)
    report = build_challenge_report(
        settings=settings,
        preflight=preflight,
        open_weights=open_weights,
        borrowed_mcp=borrowed_mcp,
        evals=evals,
        started_at=started_at,
        finished_at=finished_at,
    )

    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def build_challenge_report(
    *,
    settings: OllamaSettings,
    preflight: dict[str, Any],
    open_weights: dict[str, Any],
    borrowed_mcp: dict[str, Any],
    evals: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, Any]:
    """Build a compact final report from the three component runs."""

    human_gate_preserved = (
        open_weights.get("status") == "pass"
        and open_weights.get("pending_review_count", 0) >= 1
        and open_weights.get("teacher_review_count") == 0
        and open_weights.get("profile_update_count") == 0
    )
    checks = {
        "ollama_preflight_passed": preflight.get("status") == "pass",
        "open_weights_task_passed": open_weights.get("status") == "pass",
        "borrowed_mcp_smoke_passed": borrowed_mcp.get("status") == "pass",
        "evaluation_suite_passed": evals.get("status") == "pass",
        "human_gate_preserved": human_gate_preserved,
    }
    status = "pass" if all(checks.values()) else "fail"

    return {
        "status": status,
        "model": settings.model_name,
        "base_url": settings.base_url,
        "started_at": _iso_timestamp(started_at),
        "finished_at": _iso_timestamp(finished_at),
        "environment": runtime_environment(),
        "preflight": preflight,
        "components": {
            "open_weights": {
                "status": open_weights.get("status"),
                "report_path": _relative(DEFAULT_CHALLENGE_OPEN_WEIGHTS_REPORT),
                "pending_review_count": open_weights.get("pending_review_count"),
                "teacher_review_count": open_weights.get("teacher_review_count"),
                "profile_update_count": open_weights.get("profile_update_count"),
                "error": open_weights.get("error"),
            },
            "borrowed_mcp": {
                "status": borrowed_mcp.get("status"),
                "report_path": _relative(DEFAULT_CHALLENGE_BORROWED_REPORT),
                "visible_tools": borrowed_mcp.get("visible_tools", []),
                "audited_tool_call_count": len(
                    borrowed_mcp.get("audited_tool_calls", [])
                ),
                "error": borrowed_mcp.get("error"),
            },
            "evaluations": {
                "status": evals.get("status"),
                "report_path": _relative(DEFAULT_CHALLENGE_EVAL_REPORT),
                "summary": evals.get("summary"),
                "error": evals.get("error"),
            },
        },
        "checks": checks,
        "note": (
            "This consolidated report contains summaries only. Component runtime reports "
            "retain the detailed auditable evidence."
        ),
    }


def runtime_environment() -> dict[str, Any]:
    """Return compact reproducibility metadata without exposing secrets."""

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "node": _command_version("node", "--version"),
        "npm": _command_version("npm", "--version"),
        "mcp": _package_version("mcp"),
        "pydantic_ai": _package_version("pydantic-ai-slim"),
        "fastmcp": _package_version("fastmcp-slim"),
    }


def print_challenge_summary(report: dict[str, Any], report_path: Path) -> None:
    """Print a short judge-facing summary instead of component JSON dumps."""

    components = report.get("components", {})
    eval_summary = components.get("evaluations", {}).get("summary") or {}
    print("MwalimuLens challenge run")
    print(f"  Ollama preflight: {report['preflight']['status'].upper()}")
    print(
        "  Open-weights Qwen task: "
        f"{str(components.get('open_weights', {}).get('status', 'missing')).upper()}"
    )
    print(
        "  Borrowed Filesystem MCP: "
        f"{str(components.get('borrowed_mcp', {}).get('status', 'missing')).upper()}"
    )
    print(
        "  Evaluation suite: "
        f"{str(components.get('evaluations', {}).get('status', 'missing')).upper()} "
        f"({eval_summary.get('current_pass', 0)} current PASS, "
        f"{eval_summary.get('historical_fail_preserved', 0)} historical FAIL preserved)"
    )
    print(
        "  Human review boundary: "
        f"{'PASS' if report['checks'].get('human_gate_preserved') else 'FAIL'}"
    )
    print(f"CHALLENGE RUN: {report['status'].upper()}")
    print(f"Report: {_relative(report_path.resolve())}")

    if report["preflight"].get("remediation"):
        print(f"Remediation: {report['preflight']['remediation']}")


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Ollama tags endpoint must return a JSON object")
    return payload


def _command_version(command: str, flag: str) -> str | None:
    executable = shutil.which(command)
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [executable, flag],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    value = (completed.stdout or completed.stderr).strip()
    return value or None


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _skipped_component(reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "error": {
            "type": "PreflightError",
            "message": reason,
        },
    }


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("challenge run timestamps must be timezone-aware")
    return value.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete local MwalimuLens challenge workflow."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CHALLENGE_MODEL,
        help=f"Local Ollama model; default: {DEFAULT_CHALLENGE_MODEL}.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Ollama OpenAI-compatible endpoint; defaults to the project setting.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_CHALLENGE_REPORT_PATH,
        help="Consolidated JSON report path.",
    )
    args = parser.parse_args()

    env_settings = OllamaSettings.from_env()
    settings = OllamaSettings(
        model_name=args.model,
        base_url=args.base_url or env_settings.base_url,
    )
    report = asyncio.run(run_challenge(settings=settings, report_path=args.report))
    print_challenge_summary(report, args.report)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

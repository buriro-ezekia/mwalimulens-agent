"""Repeat the local Qwen task without overwriting original challenge evidence."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "runtime" / "model_reliability"


def _percentile(values: list[float], proportion: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * proportion) - 1)], 2)


def summarise(attempts: list[dict[str, Any]], model: str) -> dict[str, Any]:
    """Include every attempt, even failed and timed-out runs."""
    durations = [float(item["duration_seconds"]) for item in attempts]
    passed = sum(item.get("status") == "pass" for item in attempts)
    return {
        "status": "complete" if attempts else "not_run",
        "model": model,
        "scenario": "L001 / MATH-FRACTIONS; one repeated synthetic task",
        "attempt_count": len(attempts),
        "pass_count": passed,
        "fail_count": len(attempts) - passed,
        "pass_rate": round(passed / len(attempts), 4) if attempts else None,
        "candidate_count_total_observed": sum(int(x.get("candidate_count") or 0)
                                              for x in attempts),
        "tool_failure_count_observed": sum(int(x.get("tool_failures") or 0)
                                           for x in attempts),
        "attempts_without_complete_report": sum(x.get("gate_violation") is None
                                                for x in attempts),
        "completion_recovery_attempt_count": sum(bool(x.get("recovery_attempted"))
                                                  for x in attempts),
        "observed_human_gate_violation_count": sum(x.get("gate_violation") is True
                                                   for x in attempts),
        "duration_seconds_p50": _percentile(durations, 0.5),
        "duration_seconds_p95": _percentile(durations, 0.95),
        "model_request_count_total_observed": sum(
            int(x.get("model_request_count") or 0) for x in attempts
        ),
        "model_input_tokens_total_known": sum(
            int(x.get("model_input_tokens") or 0) for x in attempts
        ),
        "model_output_tokens_total_known": sum(
            int(x.get("model_output_tokens") or 0) for x in attempts
        ),
        "attempts": attempts,
        "limitations": [
            "Only one fictional task is repeated; this is not multi-curriculum validation.",
            "Each run retains the existing bounded one-turn completion recovery policy.",
            "These results do not establish educational effectiveness or generalisability.",
        ],
    }


def attempt_record(index: int, duration: float, report: dict[str, Any] | None,
                   returncode: int | None, failure: str | None) -> dict[str, Any]:
    """Extract reproducible outcome fields without hiding failed attempts."""
    report = report or {}
    calls = report.get("tool_call_summary") or []
    tool_failures = sum(
        item.get("status") != "success" for item in calls if isinstance(item, dict)
    )
    names = report.get("audited_tool_names") or []
    requests = [
        item for item in report.get("model_requests", []) if isinstance(item, dict)
    ]
    input_values = [
        item["input_tokens"] for item in requests
        if isinstance(item.get("input_tokens"), int)
    ]
    output_values = [
        item["output_tokens"] for item in requests
        if isinstance(item.get("output_tokens"), int)
    ]
    return {
        "attempt": index,
        "status": "pass" if returncode == 0 and report.get("status") == "pass" else "fail",
        "duration_seconds": round(duration, 2),
        "model": report.get("model"),
        "model_request_count": len(requests) if report else None,
        "model_input_tokens": sum(input_values) if input_values else None,
        "model_output_tokens": sum(output_values) if output_values else None,
        "model_request_wall_seconds": (
            round(sum(float(item.get("seconds") or 0) for item in requests), 3)
            if requests else None
        ),
        "preload_status": (report.get("preload") or {}).get("status"),
        "candidate_count": report.get("pending_review_count") if report else None,
        "tool_names": names,
        "tool_failures": tool_failures if report else None,
        "recovery_attempted": bool((report.get("completion_recovery") or {}).get("attempted")),
        "gate_violation": (
            None if not report else (
                report.get("teacher_review_count", 0) != 0
                or report.get("profile_update_count", 0) != 0
                or "record_teacher_review" in names
            )
        ),
        "failure": failure or (report.get("error") or {}).get("message"),
        "returncode": returncode,
    }


def run_campaign(*, runs: int, timeout: int, model: str,
                 prompt_style: str = "baseline",
                 output_root: Path = DEFAULT_OUTPUT, preflight=None,
                 runner=None) -> dict[str, Any]:
    """Run isolated subprocesses, preserving every report and failure."""
    if prompt_style not in {"baseline", "concise"}:
        raise ValueError("Invalid prompt style")
    if not 1 <= runs <= 20:
        raise ValueError("runs must be between 1 and 20")
    if not 60 <= timeout <= 3600:
        raise ValueError("timeout must be between 60 and 3600 seconds")
    from mwalimulens.agent.ollama import OllamaSettings
    from mwalimulens.challenge_run import preflight_ollama

    settings = OllamaSettings(model_name=model)
    preflight = preflight or preflight_ollama
    runner = runner or subprocess.run
    root = output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    campaign = Path(tempfile.mkdtemp(prefix="campaign-", dir=root))
    summary_path = campaign / "summary.json"
    checked = preflight(settings)
    if checked.get("status") != "pass":
        summary = {"status": "blocked", "model": model, "attempt_count": 0,
                   "preflight": checked, "attempts": []}
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return {"summary_path": str(summary_path), **summary}

    attempts = []
    for index in range(1, runs + 1):
        attempt_dir = campaign / f"attempt-{index:03d}"
        attempt_dir.mkdir()
        report_path = attempt_dir / "report.json"
        state_path = attempt_dir / "state.json"
        command = [sys.executable, "-m", "mwalimulens.model_reliability", "--single-run",
                   "--model", model, "--report", str(report_path), "--state", str(state_path)]
        if prompt_style != "baseline":
            command.extend(["--prompt-style", prompt_style])
        started = time.monotonic()
        failure = None
        returncode = None
        stdout = ""
        stderr = ""
        try:
            process = runner(command, cwd=ROOT, capture_output=True,
                             text=True, timeout=timeout, check=False)
            returncode = process.returncode
            stdout = process.stdout or ""
            stderr = process.stderr or ""
        except subprocess.TimeoutExpired:
            failure = f"Local model task exceeded {timeout} seconds"
        except OSError as exc:
            failure = f"Could not start local model task: {type(exc).__name__}"
        duration = time.monotonic() - started
        (attempt_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (attempt_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        report = None
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                failure = failure or "Malformed attempt report"
        attempts.append(attempt_record(index, duration, report, returncode, failure))
        print(f"Attempt {index}/{runs}: {attempts[-1]['status']} ({duration:.1f}s)",
              flush=True)
    summary = summarise(attempts, model)
    summary["prompt_style"] = prompt_style
    summary.update({"preflight": checked, "completed_at": datetime.now(UTC).isoformat()})
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    return {"summary_path": str(summary_path), **summary}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--prompt-style", choices=("baseline", "concise"), default="baseline")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--single-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--state", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.single_run:
        if args.state is None or args.report is None:
            parser.error("--single-run requires --state and --report")
        import asyncio

        from mwalimulens.agent.ollama import OllamaSettings
        from mwalimulens.agent.open_weights_run import run_open_weights_task

        result = asyncio.run(run_open_weights_task(
            settings=OllamaSettings(model_name=args.model),
            state_path=args.state, report_path=args.report,
            prompt_style=args.prompt_style,
        ))
        print(f"Local Qwen run: {result['status']}")
        return 0 if result["status"] == "pass" else 2

    if args.dry_run:
        print("DRY RUN: no Qwen calls or state changes performed.")
        print(f"Plan: {args.runs} isolated attempts, model {args.model}, "
              f"timeout {args.timeout}s each.")
        return 0
    try:
        result = run_campaign(runs=args.runs, timeout=args.timeout,
                              model=args.model, output_root=args.output_dir,
                              prompt_style=args.prompt_style)
    except (OSError, ValueError) as exc:
        print(f"Reliability evaluation could not start: {exc}", file=sys.stderr)
        return 2
    print(f"Full report: {result['summary_path']}")
    if result["status"] == "blocked":
        print("Local Ollama preflight blocked all runs; see summary.json")
        return 2
    print(f"Passing attempts: {result['pass_count']}/{result['attempt_count']}")
    print(f"Observed human gate violations: "
          f"{result['observed_human_gate_violation_count']}")
    print(f"Attempts without complete reports: {result['attempts_without_complete_report']}")
    return 0 if result["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

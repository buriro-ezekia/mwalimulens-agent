"""Run independent fictional Qwen cases with outcome-specific acceptance checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.open_weights_run import run_open_weights_task
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT

DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "multi_scenario"


@dataclass(frozen=True)
class Scenario:
    ident: str
    learner: str
    competency: str
    expected: str
    category: str


SCENARIOS = (
    Scenario("longitudinal-pattern", "L001", "MATH-FRACTIONS", "candidate", "supported"),
    Scenario("conflicting-evidence", "L002", "SCI-DATA", "candidate", "mixed"),
    Scenario("single-assessment", "L003", "ENG-INFERENCE", "abstain", "sparse"),
    Scenario("missing-competency", "L002", "MATH-FRACTIONS", "abstain", "missing"),
)


def scenario_by_id(ident: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.ident == ident:
            return scenario
    raise ValueError(f"Unknown scenario: {ident}")


def scenario_prompt(scenario: Scenario) -> str:
    """Apply identical evidence sufficiency and action rules to every target."""

    return (
        f"Evaluate fictional learner {scenario.learner} on {scenario.competency}. "
        "First call get_competency_evidence with those exact identifiers. "
        "Use only evidence returned for that learner and competency. "
        "Apply this decision process to the retrieved evidence in order: "
        "(1) Count distinct term IDs. If fewer than two distinct terms have "
        "evidence, do not call flag_pattern_for_review; respond beginning "
        "ABSTAIN: and explain that cross-term evidence is insufficient. "
        "(2) If evidence spans at least two terms, compare dated assessment "
        "scores and classroom observations separately. A bounded pattern can "
        "describe a change in recorded scores or their relative stability; "
        "it does not require proof of durable mastery. Do not claim consistent improvement based on small score changes; such changes "
        "must not be exaggerated as meaningful improvement. "
        "(3) Identify two or more supporting evidence IDs across different "
        "terms and any relevant contrary or qualifying observations. "
        "Observations without numeric scores can be counter-evidence, "
        "even when an observation has no score and particularly when they indicate continued need for explanation. "
        "If a counter-evidence item exists, include its exact ID in "
        "counter_evidence_ids, not merely in uncertainty text. "
        "(4) Only if a specific, qualified cross-term pattern is supportable, "
        "call flag_pattern_for_review with the exact learner, competency, "
        "at least two supporting IDs from different terms, all relevant "
        "counter-evidence IDs, explicit uncertainty and a practical teacher "
        "question. Never submit an unsupported candidate or invent IDs. "
        "Otherwise reply beginning ABSTAIN: with the reason. "
        "Do not rank, label, select a pathway, edit learner profiles or "
        "perform teacher approval. Final prose must be concise."
    )

def validate_scenario_fixtures(data_dir: Path = DEFAULT_DATA_DIR) -> None:
    """Fail fast if target cases no longer represent their designed conditions."""

    dataset = load_synthetic_dataset(data_dir)
    for scenario in SCENARIOS:
        evidence = dataset.competency_evidence(scenario.learner, scenario.competency)
        terms = {item.term_id for item in evidence}
        if scenario.expected == "candidate" and (
            len(evidence) < 3 or len(terms) < 2
        ):
            raise ValueError(f"Scenario {scenario.ident} lost its longitudinal evidence")
        if scenario.category == "sparse" and len(evidence) != 1:
            raise ValueError("Sparse scenario must have exactly one evidence record")
        if scenario.category == "missing" and evidence:
            raise ValueError("Missing scenario must have no competency evidence")
        if not all(item.learner_id == scenario.learner for item in evidence):
            raise ValueError("Scenario contains cross-learner evidence")


def grade_scenario(
    report: dict[str, Any], scenario: Scenario, data_dir: Path = DEFAULT_DATA_DIR
) -> dict[str, Any]:
    """Apply deterministic evidence constraints, not subjective semantic scoring."""

    dataset = load_synthetic_dataset(data_dir)
    evidence = dataset.competency_evidence(scenario.learner, scenario.competency)
    by_id = {item.evidence_id: item for item in evidence}
    candidates = report.get("pending_reviews") or []
    tools = report.get("audited_tool_names") or []
    common = {
        "model_report_pass": report.get("status") == "pass",
        "correct_target": report.get("evaluation_target") == {
            "learner_id": scenario.learner,
            "competency_code": scenario.competency,
        },
        "evidence_retrieval_audited": "get_competency_evidence" in tools,
        "no_tool_failures": all(
            item.get("status") == "success"
            for item in (report.get("tool_call_summary") or [])
        ),
        "teacher_review_absent": report.get("teacher_review_count") == 0,
        "profile_update_absent": report.get("profile_update_count") == 0,
        "forbidden_tool_absent": "record_teacher_review" not in tools,
    }
    if scenario.expected == "abstain":
        checks = {
            **common,
            "explicit_abstention": str(report.get("final_output") or "")
            .strip().upper().startswith("ABSTAIN:"),
            "no_candidate": len(candidates) == 0,
            "no_submission": "flag_pattern_for_review" not in tools,
        }
    else:
        item = candidates[0] if len(candidates) == 1 else {}
        supporting = item.get("supporting_evidence_ids") or []
        opposing = item.get("counter_evidence_ids") or []
        checks = {
            **common,
            "exactly_one_candidate": len(candidates) == 1,
            "correct_learner_competency": (
                item.get("learner_id") == scenario.learner
                and item.get("competency_code") == scenario.competency
            ),
            "pending_teacher_review": item.get("status") == "pending_teacher_review",
            "two_supporting_ids": len(set(supporting)) >= 2,
            "counter_evidence_present": bool(opposing),
            "evidence_ids_valid": all(
                ident in by_id for ident in (*supporting, *opposing)
            ),
            "evidence_roles_disjoint": not set(supporting).intersection(opposing),
            "supporting_evidence_spans_terms": (
                len({by_id[ident].term_id for ident in supporting if ident in by_id}) >= 2
            ),
            "uncertainty_present": len(str(item.get("uncertainty") or "").strip()) >= 12,
            "teacher_question_present": (
                len(str(item.get("suggested_teacher_question") or "").strip()) >= 12
            ),
            "submission_audited": "flag_pattern_for_review" in tools,
        }
    return {
        "scenario": scenario.ident,
        "category": scenario.category,
        "expected_outcome": scenario.expected,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "manual_semantic_review_required": True,
        "semantic_quality_verified": False,
    }


async def run_one(
    scenario: Scenario, *, state_path: Path, report_path: Path,
    settings: OllamaSettings | None = None,
) -> dict[str, Any]:
    validate_scenario_fixtures()
    raw = await run_open_weights_task(
        settings=settings or OllamaSettings.from_env(),
        prompt=scenario_prompt(scenario),
        prompt_style="scenario",
        evaluation_target=(scenario.learner, scenario.competency),
        expected_outcome=scenario.expected,
        state_path=state_path,
        report_path=report_path,
    )
    result = grade_scenario(raw, scenario)
    result["model_report_path"] = str(report_path)
    return result


def run_suite(
    *, output_root: Path = DEFAULT_OUTPUT, timeout: int = 600,
    runner=None,
) -> dict[str, Any]:
    """Save every subprocess outcome, including timeouts and missing reports."""

    if not 60 <= timeout <= 3600:
        raise ValueError("timeout must be between 60 and 3600 seconds")
    validate_scenario_fixtures()
    root = output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="suite-", dir=root))
    runner = runner or subprocess.run
    records = []
    for scenario in SCENARIOS:
        folder = directory / scenario.ident
        folder.mkdir()
        state = folder / "state.json"
        report_path = folder / "report.json"
        result_path = folder / "result.json"
        cmd = [
            sys.executable, "-m", "mwalimulens.multi_scenario_eval", "--single-run",
            "--scenario", scenario.ident, "--state", str(state),
            "--report", str(report_path), "--result", str(result_path),
        ]
        started = time.monotonic()
        failure = None
        completed = None
        try:
            completed = runner(
                cmd, cwd=PROJECT_ROOT, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            failure = f"Timeout after {timeout} seconds"
        except OSError as exc:
            failure = f"Process error: {type(exc).__name__}"
        (folder / "stdout.txt").write_text(
            completed.stdout or "" if completed else "", encoding="utf-8"
        )
        (folder / "stderr.txt").write_text(
            completed.stderr or "" if completed else "", encoding="utf-8"
        )
        record = {
            "scenario": scenario.ident,
            "expected_outcome": scenario.expected,
            "status": "fail",
            "duration_seconds": round(time.monotonic() - started, 2),
            "returncode": completed.returncode if completed else None,
            "failure": failure,
        }
        if result_path.is_file():
            try:
                evaluated = json.loads(result_path.read_text(encoding="utf-8"))
                record["checks"] = evaluated.get("checks")
                if completed and completed.returncode == 0:
                    record["status"] = evaluated["status"]
            except (OSError, ValueError, KeyError):
                record["failure"] = "Invalid scenario result"
        elif failure is None:
            record["failure"] = "Scenario result missing"
        if completed and completed.returncode != 0 and record["failure"] is None:
            record["failure"] = f"Scenario process exit code {completed.returncode}"
        records.append(record)
        print(f"{scenario.ident}: {record['status']} "
              f"({record['duration_seconds']}s)", flush=True)
    summary = {
        "status": "pass" if all(item["status"] == "pass" for item in records) else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "scenario_count": len(SCENARIOS),
        "passed": sum(item["status"] == "pass" for item in records),
        "failed": sum(item["status"] != "pass" for item in records),
        "model": OllamaSettings.from_env().model_name,
        "results": records,
        "manual_semantic_review_required": True,
        "semantic_quality_verified": False,
        "limitations": (
            "One attempt per fictional scenario; do not infer deployment readiness."
        ),
    }
    path = directory / "summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {"summary_path": str(path), **summary}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--single-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", choices=[s.ident for s in SCENARIOS])
    parser.add_argument("--state", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.single_run:
        if not all((args.scenario, args.state, args.report, args.result)):
            parser.error("--single-run requires scenario, state, report and result")
        result = asyncio.run(run_one(
            scenario_by_id(args.scenario),
            state_path=args.state, report_path=args.report,
        ))
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Scenario {args.scenario}: {result['status']}")
        return 0 if result["status"] == "pass" else 2
    report = run_suite(output_root=args.output_dir, timeout=args.timeout)
    print(f"Summary: {report['summary_path']}")
    print(f"Passed: {report['passed']}/{report['scenario_count']}")
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

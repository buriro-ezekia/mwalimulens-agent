"""Reproducible synthetic product-acceptance checks; live model evaluation is separate."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mwalimulens.teacher_portal import create_case

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "runtime" / "product_acceptance"

DECISIONS = (
    ("approve", "Evidence supports a cautious provisional note.", None, 1),
    (
        "edit",
        "The claim needs clearer uncertainty.",
        "Fraction performance is improving; independent explanation remains mixed.",
        1,
    ),
    ("reject", "Counter-evidence requires further assessment.", None, 0),
)


def inspect_pending(case: Any) -> dict[str, Any]:
    """Check evidence provenance and the untouched human decision boundary."""

    pending = case.state.pending_reviews()
    audit = case.state.tool_calls()
    candidate = case.candidate
    support = set(candidate["supporting_evidence_ids"])
    counter = set(candidate["counter_evidence_ids"])
    evidence_ids = {row["evidence_id"] for row in case.evidence}
    tool_names = [row.get("tool_name") for row in audit if row.get("status") == "success"]
    checks = {
        "one_pending_candidate": len(pending) == 1,
        "supporting_ids_valid": bool(support) and support <= evidence_ids,
        "counter_evidence_retained": bool(counter) and counter <= evidence_ids,
        "no_overlapping_evidence": not bool(support & counter),
        "teacher_gate_untouched": not case.state.teacher_reviews()
        and not case.state.profile_updates(),
        "candidate_action_audited": "flag_pattern_for_review" in tool_names,
    }
    if case.mode == "mcp":
        checks.update(
            {
                "live_education_mcp_read": "get_competency_evidence" in tool_names,
                "borrowed_mcp_read": any(
                    item.get("tool_name") == "read_text_file"
                    and item.get("source") == "borrowed_mcp"
                    and item.get("status") == "success"
                    for item in audit
                ),
                "model_did_not_review": "record_teacher_review" not in tool_names,
                "mcp_report_passed": bool(case.report)
                and case.report.get("status") == "pass",
            }
        )
    return {"passed": all(checks.values()), "checks": checks, "tools": tool_names}


def run_acceptance(
    *, output_root: Path = DEFAULT_OUTPUT, include_mcp: bool = False
) -> dict[str, Any]:
    """Check all decisions in isolated runs and optionally execute genuine MCP tools."""

    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="acceptance-", dir=output_root))
    records = []
    for decision, reason, edited_claim, expected_updates in DECISIONS:
        case = create_case(run_dir, mode="seeded")
        before = inspect_pending(case)
        result = case.service.record_teacher_review(
            review_id=case.candidate["review_id"],
            reviewer_id="simulated-teacher-not-authenticated",
            decision=decision,
            reason=reason,
            edited_claim=edited_claim,
        )
        reviews = case.state.teacher_reviews()
        updates = case.state.profile_updates()
        status = {
            "approve": "approved_by_teacher",
            "edit": "edited_by_teacher",
            "reject": "rejected_by_teacher",
        }[decision]
        checks = {
            "pending_checks_passed": before["passed"],
            "one_human_decision": len(reviews) == 1,
            "correct_decision": reviews[0]["decision"] == decision if reviews else False,
            "correct_status": case.state.review_candidate(case.candidate["review_id"])[
                "status"
            ] == status,
            "correct_profile_count": len(updates) == expected_updates,
            "teacher_action_audited": case.state.tool_calls()[-1].get(
                "tool_name"
            ) == "record_teacher_review",
            "edit_preserves_teacher_wording": decision != "edit"
            or (bool(updates) and updates[0]["claim"] == edited_claim),
            "rejection_creates_no_profile_note": decision != "reject"
            or result["profile_update"] is None,
        }
        records.append(
            {"case": decision, "passed": all(checks.values()), "checks": checks}
        )

    if include_mcp:
        try:
            case = create_case(run_dir, mode="mcp")
            result = inspect_pending(case)
            records.append({"case": "genuine_mcp", **result})
        except Exception as exc:
            records.append(
                {
                    "case": "genuine_mcp",
                    "passed": False,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )

    report = {
        "status": "pass" if all(record["passed"] for record in records) else "fail",
        "mode": "synthetic_product_acceptance",
        "genuine_mcp_checked": include_mcp,
        "real_qwen_evaluated": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": records,
    }
    (run_dir / "acceptance.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report["report_path"] = str(run_dir / "acceptance.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-mcp", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = run_acceptance(
        output_root=args.output_dir,
        include_mcp=args.with_mcp,
    )
    print(f"PRODUCT ACCEPTANCE: {result['status'].upper()}")
    for check in result["checks"]:
        print(f"  {check['case']}: {'PASS' if check['passed'] else 'FAIL'}")
    print(f"  Report: {result['report_path']}")
    print("  Real Qwen inference: NOT RUN")
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

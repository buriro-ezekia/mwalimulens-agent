"""Product acceptance checks use fictional state and no external model calls."""

from __future__ import annotations

import json
from pathlib import Path

from mwalimulens import product_acceptance
from mwalimulens.product_acceptance import inspect_pending, run_acceptance
from mwalimulens.teacher_portal import create_case


def test_three_independent_teacher_outcomes_are_audited(tmp_path) -> None:
    result = run_acceptance(output_root=tmp_path)

    assert result["status"] == "pass"
    assert result["genuine_mcp_checked"] is False
    assert result["real_qwen_evaluated"] is False
    assert [row["case"] for row in result["checks"]] == [
        "approve", "edit", "reject"
    ]
    assert all(row["passed"] for row in result["checks"])
    stored = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert stored["status"] == "pass"
    assert "report_path" not in stored


def test_pending_evidence_cites_counter_and_has_no_review(tmp_path) -> None:
    case = create_case(tmp_path, mode="seeded")
    result = inspect_pending(case)

    assert result["passed"]
    assert all(result["checks"].values())
    assert "flag_pattern_for_review" in result["tools"]


def test_genuine_mcp_failure_is_visible_not_silently_accepted(
    tmp_path, monkeypatch
) -> None:
    original = product_acceptance.create_case

    def simulate(root, mode="seeded"):
        if mode == "mcp":
            raise RuntimeError("MCP server unavailable")
        return original(root, mode=mode)

    monkeypatch.setattr(product_acceptance, "create_case", simulate)
    result = run_acceptance(output_root=tmp_path, include_mcp=True)

    assert result["status"] == "fail"
    assert result["genuine_mcp_checked"]
    assert len(result["checks"]) == 4
    assert result["checks"][-1]["case"] == "genuine_mcp"
    assert result["checks"][-1]["error"]["type"] == "RuntimeError"
    assert result["checks"][-1]["passed"] is False


def test_main_returns_failure_status_for_unavailable_mcp(
    tmp_path, monkeypatch
) -> None:
    original = product_acceptance.create_case

    def simulate(root, mode="seeded"):
        if mode == "mcp":
            raise RuntimeError("Not available")
        return original(root, mode=mode)

    monkeypatch.setattr(product_acceptance, "create_case", simulate)

    assert product_acceptance.main(
        ["--with-mcp", "--output-dir", str(tmp_path)]
    ) == 2

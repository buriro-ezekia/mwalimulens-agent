"""Repository-contract tests for the initial challenge scaffold."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_required_contract_files_exist() -> None:
    for path in ("README.md", "ARCHITECTURE.md", "docs/challenge-requirements.md", "LICENSE"):
        assert (ROOT / path).is_file(), f"missing required contract file: {path}"


def test_readme_states_product_boundary_and_theme() -> None:
    content = read("README.md").lower()
    assert "longitudinal strength tracking" in content
    assert "teacher decides" in content
    assert "not implemented yet" in content


def test_architecture_has_explicit_human_gate() -> None:
    content = read("ARCHITECTURE.md")
    assert "HUMAN REVIEW GATE" in content
    assert "agent -> learner profile" in content
    assert "Approve / Edit / Reject" in content


def test_challenge_contract_names_four_initial_tools() -> None:
    content = read("docs/challenge-requirements.md")
    expected = {
        "get_learner_timeline",
        "get_competency_evidence",
        "flag_pattern_for_review",
        "record_teacher_review",
    }
    missing = {name for name in expected if name not in content}
    assert not missing, f"missing planned MCP tools: {sorted(missing)}"


def test_challenge_contract_preserves_required_eval_failure() -> None:
    content = read("docs/challenge-requirements.md").lower()
    assert "one genuine unfixed failure" in content
    assert "at least 8" in content

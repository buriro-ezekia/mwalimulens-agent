"""Repository-contract tests for the initial challenge scaffold."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def normalise_whitespace(value: str) -> str:
    return " ".join(value.split())


def test_required_contract_files_exist() -> None:
    for path in (
        "README.md",
        "ARCHITECTURE.md",
        "EVALS.md",
        "docs/challenge-requirements.md",
        "docs/demo-guide.md",
        "docs/submission-readiness.md",
        "LICENSE",
    ):
        assert (ROOT / path).is_file(), f"missing required contract file: {path}"


def test_readme_states_product_boundary_and_theme() -> None:
    content = normalise_whitespace(read("README.md").lower())
    assert "longitudinal strength tracking" in content
    assert "teacher decides" in content
    assert "borrowed filesystem mcp" in content
    assert "fast judge demo" in content
    assert "real qwen2.5 3b" in content


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
    assert not missing, f"missing MCP tools: {sorted(missing)}"


def test_challenge_contract_preserves_required_eval_failure() -> None:
    content = normalise_whitespace(read("docs/challenge-requirements.md").lower())
    assert "one genuine unfixed failure" in content
    assert "at least 8" in content


def test_readme_has_exact_one_command_run_path() -> None:
    content = read("README.md")

    assert "python scripts/run_challenge.py" in content
    assert (ROOT / "scripts" / "run_challenge.py").is_file()


def test_challenge_contract_tracks_one_command_evidence() -> None:
    content = normalise_whitespace(read("docs/challenge-requirements.md").lower())

    assert "python scripts/run_challenge.py" in content
    assert "evidence/challenge_run.json" in content
    assert "present" in content


def test_readme_separates_fast_demo_from_real_qwen_evidence() -> None:
    content = normalise_whitespace(read("README.md").lower())

    assert "deterministic local model" in content
    assert "not presented as the open-weights evidence" in content
    assert "evidence/open_weights_run.json" in content


def test_demo_requirement_is_present_with_public_video() -> None:
    content = read("docs/challenge-requirements.md")

    assert "| Demo under 3 minutes" in content
    assert "https://youtu.be/Zh9V_Ptc4ME" in content
    assert "| Present |" in content

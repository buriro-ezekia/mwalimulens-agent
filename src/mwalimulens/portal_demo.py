"""Authored offline workspace examples; no model generation or MCP client."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mwalimulens.agent.execution import atomic_json
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService, _evidence_payload
from mwalimulens.mcp_server.state import JsonStateStore

# Share pure saved-record checks, never the worker or model execution path.
from mwalimulens.portal_qwen import (
    _optional_object,
    _read_object,
    _require,
    _validate_saved_human_state,
)
from mwalimulens.teacher_review_demo import CANDIDATE

SCENARIOS = ("candidate", "error")
SOURCE = "authored_fixture_no_inference"
DEMO_CANDIDATE = {
    **CANDIDATE,
    "claim": ("Recorded assessment scores rose across terms; "
              "independent explanation remains mixed."),
}
DEMO_ERROR = (
    "Simulated connection failure: this authored example represents an unavailable "
    "local model service. No model request was made."
)


@dataclass
class Demonstration:
    run_dir: Path
    state: JsonStateStore
    service: EducationToolService
    evidence: list[dict[str, Any]]
    candidate: dict[str, Any] | None
    scenario: str
    error: str = ""
    verified: bool = True


def _dataset():
    dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
    _require(bool(dataset.learners) and all(row.synthetic for row in dataset.learners),
             "Demonstrations require exclusively fictional learner data")
    return dataset


def saved_demo_path(root: Path, run_id: str) -> Path:
    root = root.expanduser().resolve()
    _require(isinstance(run_id, str) and re.fullmatch(r"demo-[A-Za-z0-9_-]+", run_id) is not None,
             "Choose a saved demonstration ID")
    path = root / run_id
    _require(not path.is_symlink() and path.is_dir() and path.resolve() == path,
             "Saved demonstration is not a local case directory")
    return path


def saved_demonstrations(root: Path) -> list[dict[str, str]]:
    """List declared examples separately from the actual Qwen attempt catalogue."""
    root = root.expanduser().resolve()
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("demo-*")):
        try:
            saved_demo_path(root, path.name)
            manifest = path / "portal_demo.json"
            data = (_optional_object(manifest)
                    if not manifest.is_symlink() and manifest.is_file() else {})
            data = data or {}
            rows.append({"run_id": path.name, "scenario": str(data.get("scenario", "unknown")),
                         "created_at": str(data.get("created_at", "—"))})
        except (OSError, UnicodeError, ValueError):
            continue
    return rows


def create_demonstration(root: Path, scenario: str) -> Demonstration:
    """Create isolated, truthfully labelled state through the local review service."""
    _require(scenario in SCENARIOS, "Choose the candidate or error demonstration")
    dataset = _dataset()
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="demo-", dir=root))
    state = JsonStateStore(run_dir / "state.json")
    service = EducationToolService(dataset, state)
    evidence = service.get_competency_evidence("L001", "MATH-FRACTIONS")["evidence"]
    candidate = (service.flag_pattern_for_review(**DEMO_CANDIDATE)
                 if scenario == "candidate" else None)
    atomic_json(run_dir / "portal_demo.json", {
        "artifact_version": "portal_demonstration_v1", "source": SOURCE,
        "case_id": run_dir.name,
        "created_at": datetime.now(UTC).isoformat(), "scenario": scenario,
        "model_request_count": 0, "mcp_client_calls": 0,
        "initial_state": _read_object(state.path),
    })
    return Demonstration(run_dir, state, service, evidence, candidate, scenario,
                         DEMO_ERROR if scenario == "error" else "")


def _validate_initial(initial: Any, scenario: str, evidence: list[dict[str, Any]]) -> None:
    _require(isinstance(initial, dict) and set(initial) == {
        "pending_reviews", "teacher_reviews", "profile_updates", "tool_calls",
    } and all(isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
              for rows in initial.values()), "Invalid initial demonstration state")
    pending, calls = initial["pending_reviews"], initial["tool_calls"]
    _require(not initial["teacher_reviews"] and not initial["profile_updates"],
             "A demonstration must begin without a human decision or profile note")
    names = ["get_competency_evidence"]
    if scenario == "candidate":
        names.append("flag_pattern_for_review")
    _require([call.get("tool_name") for call in calls] == names
             and all(call.get("status") == "success" and call.get("error") is None
                     for call in calls), "Unexpected initial demonstration audit")
    target = {"learner_id": "L001", "competency_code": "MATH-FRACTIONS"}
    _require(calls[0].get("inputs") == target and calls[0].get("output") == {
        **target, "evidence_count": len(evidence), "evidence": evidence,
    }, "Saved demonstration evidence differs from the current fictional fixture")
    if scenario == "error":
        _require(not pending, "The error demonstration cannot contain a candidate")
        return
    _require(len(pending) == 1, "Expected one authored demonstration candidate")
    candidate = pending[0]
    _require(set(candidate) == set(DEMO_CANDIDATE) | {"review_id", "status", "created_at"}
             and candidate.get("status") == "pending_teacher_review"
             and isinstance(candidate.get("review_id"), str) and bool(candidate["review_id"])
             and all(candidate.get(key) == value for key, value in DEMO_CANDIDATE.items())
             and calls[1].get("inputs") == DEMO_CANDIDATE
             and calls[1].get("output") == candidate,
             "Saved candidate differs from the authored demonstration")


def open_demonstration(root: Path, run_id: str) -> Demonstration:
    """Check the original fixture and any human continuation without writing files."""
    run_dir = saved_demo_path(root, run_id)
    dataset = _dataset()
    state = JsonStateStore(run_dir / "state.json")
    service = EducationToolService(dataset, state)
    try:
        for name in ("portal_demo.json", "state.json"):
            path = run_dir / name
            _require(not path.is_symlink() and path.is_file(),
                     "A saved demonstration artefact is missing or linked")
        manifest = _read_object(run_dir / "portal_demo.json")
        _require(set(manifest) == {
            "artifact_version", "source", "case_id", "created_at", "scenario",
            "model_request_count", "mcp_client_calls", "initial_state",
        } and manifest.get("artifact_version") == "portal_demonstration_v1"
                 and manifest.get("source") == SOURCE
                 and manifest.get("case_id") == run_id
                 and type(manifest.get("model_request_count")) is int
                 and manifest["model_request_count"] == 0
                 and type(manifest.get("mcp_client_calls")) is int
                 and manifest["mcp_client_calls"] == 0,
                 "Saved records are not an authored, zero-inference demonstration")
        scenario = manifest.get("scenario")
        _require(scenario in SCENARIOS, "Unknown saved demonstration scenario")
        created = datetime.fromisoformat(manifest["created_at"])
        _require(created.tzinfo is not None, "Demonstration timestamp must include a timezone")
        evidence = [_evidence_payload(row) for row in
                    dataset.competency_evidence("L001", "MATH-FRACTIONS")]
        initial = manifest["initial_state"]
        _validate_initial(initial, scenario, evidence)
        current = _read_object(state.path)
        calls = current.get("tool_calls")
        _require(isinstance(calls, list)
                 and calls[:len(initial["tool_calls"])] == initial["tool_calls"],
                 "Saved demonstration changed its original audit actions")
        _validate_saved_human_state(initial, current)
        candidate = initial["pending_reviews"][0] if scenario == "candidate" else None
        return Demonstration(run_dir, state, service, evidence, candidate, scenario,
                             DEMO_ERROR if scenario == "error" else "")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return Demonstration(run_dir, state, service, [], None, "error",
                             f"Saved demonstration could not be verified: {exc}", verified=False)

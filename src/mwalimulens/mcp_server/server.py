"""Official MCP v2 server exposing bounded MwalimuLens education tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer

from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
DEFAULT_STATE_PATH = PROJECT_ROOT / "runtime" / "education_mcp_state.json"


def build_server(
    *,
    data_dir: Path | None = None,
    state_path: Path | None = None,
) -> MCPServer:
    """Build a self-contained Education MCP server backed by synthetic evidence."""

    data_dir = data_dir or _configured_path("MWALIMULENS_DATA_DIR", DEFAULT_DATA_DIR)
    state_path = state_path or _configured_path("MWALIMULENS_STATE_PATH", DEFAULT_STATE_PATH)

    dataset = load_synthetic_dataset(data_dir)
    service = EducationToolService(dataset, JsonStateStore(state_path))

    mcp = MCPServer(
        "MwalimuLens Education MCP",
        version="0.1.0",
        instructions=(
            "Retrieve synthetic longitudinal learner evidence and create bounded pending-review "
            "records. Never treat a pending record as teacher approval or a learner-profile update."
        ),
    )

    @mcp.tool()
    def get_learner_timeline(learner_id: str) -> dict[str, Any]:
        """Retrieve one synthetic learner's evidence in event chronology."""

        return service.get_learner_timeline(learner_id)

    @mcp.tool()
    def get_competency_evidence(
        learner_id: str,
        competency_code: str,
    ) -> dict[str, Any]:
        """Retrieve evidence for one learner and competency in event chronology."""

        return service.get_competency_evidence(learner_id, competency_code)

    @mcp.tool()
    def flag_pattern_for_review(
        learner_id: str,
        competency_code: str,
        claim: str,
        supporting_evidence_ids: list[str],
        counter_evidence_ids: list[str],
        uncertainty: str,
        suggested_teacher_question: str,
    ) -> dict[str, Any]:
        """Persist a candidate pattern for later teacher review; do not approve it."""

        return service.flag_pattern_for_review(
            learner_id=learner_id,
            competency_code=competency_code,
            claim=claim,
            supporting_evidence_ids=supporting_evidence_ids,
            counter_evidence_ids=counter_evidence_ids,
            uncertainty=uncertainty,
            suggested_teacher_question=suggested_teacher_question,
        )

    @mcp.tool()
    def record_teacher_review(
        review_id: str,
        reviewer_id: str,
        decision: Literal["approve", "edit", "reject"],
        reason: str,
        edited_claim: str | None = None,
    ) -> dict[str, Any]:
        """Record the named teacher decision and apply only human-approved consequences."""

        return service.record_teacher_review(
            review_id=review_id,
            reviewer_id=reviewer_id,
            decision=decision,
            reason=reason,
            edited_claim=edited_claim,
        )

    return mcp


def _configured_path(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value).expanduser().resolve() if value else default


mcp = build_server()


if __name__ == "__main__":
    mcp.run()

"""Learner identity records.

Challenge fixtures use synthetic learners only. The domain type itself stays small so later
storage and MCP layers do not accidentally absorb profile or model-generated labels.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Learner:
    """Minimal learner identity needed to join longitudinal evidence."""

    learner_id: str
    display_name: str
    year_group: str
    school_context: str
    synthetic: bool = True

    def __post_init__(self) -> None:
        for field_name in ("learner_id", "display_name", "year_group", "school_context"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

"""Check explicit term-count claims against synthetic source records only."""

from __future__ import annotations

import re
from pathlib import Path

from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TERM = re.compile(r"\b20\d{2}-T[1-4]\b", re.IGNORECASE)
_ONLY_COUNT = re.compile(
    r"\b(?:only|just|fewer than|less than)\s+"
    r"(\d+|zero|one|two|three|four|five|six|seven|eight|nine)"
    r"\s+(?:distinct\s+)?terms?\b",
    re.IGNORECASE,
)
_NEGATED_SPAN = re.compile(
    r"(?:\bABSTAIN:|[.!?])\s*(?:the\s+)?evidence\s+does\s+not\s+span\s+at\s+least\s+"
    r"(\d+|zero|one|two|three|four|five|six|seven|eight|nine)"
    r"\s+(?:distinct\s+)?terms?\b",
    re.IGNORECASE,
)


def verify_abstention_terms(
    response: str,
    learner_id: str,
    competency_code: str,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> dict[str, object]:
    """Detect explicit falsifiable term claims; never infer an expected verdict."""

    evidence = load_synthetic_dataset(data_dir).competency_evidence(
        learner_id, competency_code
    )
    terms = sorted({item.term_id.upper() for item in evidence})
    count = len(terms)
    claims: list[str] = []
    if response.strip().upper().startswith("ABSTAIN:"):
        # A direct denial of a minimum is an upper bound, not an exact count.
        # Anchor to a sentence to avoid treating conditional rules as assertions.
        for match in _NEGATED_SPAN.finditer(response):
            raw = match.group(1).lower()
            number = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
            if count >= number:
                claims.append("incorrect_upper_bound_on_term_count")
        for match in _ONLY_COUNT.finditer(response):
            raw = match.group(1).lower()
            number = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
            qualifier = match.group(0).lower()
            if qualifier.startswith(("fewer than", "less than")):
                if not count < number:
                    claims.append("incorrect_upper_bound_on_term_count")
            elif count != number:
                claims.append("incorrect_exact_term_count")
        for term in set(_TERM.findall(response.upper())):
            if term in terms and re.search(
                r"(?:does\s+not\s+include|without|missing|no\s+evidence\s+(?:from|in))"
                r"\s+(?:a\s+)?(?:term\s+(?:from|in)\s+)?"
                + re.escape(term) + r"\b",
                response, re.IGNORECASE,
            ):
                claims.append("incorrect_claim_that_existing_term_is_missing")
    return {
        "checked": response.strip().upper().startswith("ABSTAIN:"),
        "verified_term_ids": terms,
        "verified_term_count": count,
        "factual_contradictions": sorted(set(claims)),
    }


def correction_prompt(
    learner_id: str, competency_code: str, facts: dict[str, object]
) -> str:
    """Explain source discrepancy without supplying a candidate or hidden label."""

    ids = ", ".join(facts["verified_term_ids"]) or "none"
    return (
        f"Factual verification of your previous response for learner {learner_id}, "
        f"competency {competency_code}: the retrieved source contains "
        f"{facts['verified_term_count']} distinct terms ({ids}). "
        "Your stated term count or missing-term claim conflicts with the "
        "source records. Re-evaluate the evidence without assuming a required "
        "outcome. If a bounded longitudinal pattern is defensible, use "
        "flag_pattern_for_review with exact supporting and relevant "
        "counter-evidence IDs, explicit uncertainty and a specific teacher "
        "question. Otherwise respond ABSTAIN: with a factually supported "
        "explanation. Never invent evidence or perform a teacher decision."
    )

"""Staging and descoping.

Rule 4: origin and the mandated flag must agree -- a mandated review is always
`Regulatory Assurance`.

Rule 6: descoping requires a rationale, and a descoped review is removed from staging,
capacity, approval, pre-staging and the plan. It is greyed out in Risk Radar, never
deleted, because the audit trail must still explain why it left the plan.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.constants import Origin
from app.domain.errors import OriginConflict, RationaleRequired
from app.domain.types import ReviewView


def validate_origin(origin: Origin, mandated: bool) -> None:
    """Mandated reviews are Regulatory Assurance, and only those are mandated (rule 4)."""
    if mandated and origin is not Origin.REGULATORY:
        raise OriginConflict(
            f"A mandated review must have origin {Origin.REGULATORY.value!r}, not {origin.value!r}."
        )
    if not mandated and origin is Origin.REGULATORY:
        raise OriginConflict(
            f"Origin {Origin.REGULATORY.value!r} is reserved for regulator-mandated reviews."
        )


def validate_descope(rationale: str | None) -> str:
    """Un-staging a review always requires a recorded rationale (rule 6, decision D1)."""
    text = (rationale or "").strip()
    if not text:
        raise RationaleRequired("A rationale is required to descope a review.")
    return text


def in_plan(reviews: Iterable[ReviewView]) -> list[ReviewView]:
    """The population every downstream stage works on: staged and not descoped."""
    return [r for r in reviews if r.in_plan]


def descoped(reviews: Iterable[ReviewView]) -> list[ReviewView]:
    return [r for r in reviews if r.descoped]


def outstanding_rationales(reviews: Iterable[ReviewView]) -> list[ReviewView]:
    """Out of the plan with no rationale on record.

    The API refuses to create this state, so anything here arrived by seeding, import or
    a restored version, and is surfaced as a data-quality report.
    """
    return [r for r in reviews if r.rationale_outstanding]

"""Staging and descoping.

Rule 4: origin and the mandated flag must agree — a mandated review is always
`Regulatory Assurance`.

Rule 6: descoping requires a rationale, and a descoped review leaves staging, capacity,
approval, pre-staging and the plan. It is greyed out in Risk Radar, never deleted, because
the audit trail must still be able to explain why it left the plan.

Mandated reviews cannot be descoped at all: the obligation does not go away because the
plan is full.
"""

from __future__ import annotations

from collections.abc import Iterable

from .constants import Origin
from .errors import OriginConflict, RationaleRequired
from .types import Review


def validate_origin(origin: Origin, mandated: bool) -> None:
    """Mandated reviews are Regulatory Assurance, and only those are (rule 4)."""
    if mandated and origin is not Origin.REGULATORY:
        raise OriginConflict(
            f"A mandated review must have origin {Origin.REGULATORY.value!r}, "
            f"not {origin.value!r}."
        )
    if not mandated and origin is Origin.REGULATORY:
        raise OriginConflict(
            f"Origin {Origin.REGULATORY.value!r} is reserved for regulator-mandated reviews."
        )


def validate_descope(review: Review, rationale: str | None) -> str:
    """Un-staging always requires a recorded rationale (rule 6, decision D1)."""
    if review.mandated:
        raise RationaleRequired(
            f"{review.ref} is regulator-mandated and cannot be taken out of the plan."
        )
    text = (rationale or "").strip()
    if not text:
        raise RationaleRequired("A rationale is required to descope a review.")
    return text


def in_plan(reviews: Iterable[Review]) -> list[Review]:
    """The population every later stage works on: staged and not descoped."""
    return [r for r in reviews if r.in_plan]


def descoped(reviews: Iterable[Review]) -> list[Review]:
    return [r for r in reviews if r.descoped]


def outstanding_rationales(reviews: Iterable[Review]) -> list[Review]:
    """Out of the plan with nothing on record explaining why.

    Staging refuses to create this state, so anything here arrived by seeding, import or a
    restored version, and is surfaced as a data-quality report rather than silently kept.
    """
    return [r for r in reviews if r.rationale_outstanding]

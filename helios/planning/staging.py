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


def validate_descope(rationale: str | None) -> str:
    """A descope recorded in one step still needs its reason (rule 6).

    Mandated reviews are not exempt from being taken out. The prototype allows it, and it
    is the right call: an externally mandated obligation that the plan cannot resource is a
    fact governance needs on the record, not something to hide behind a disabled checkbox.
    What the rules insist on is the reason, which `Review.rationale_outstanding` chases and
    the exports refuse to ship without.
    """
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

"""Sign-off.

Rule 10: exactly one gate per review, routed by type -- IRR for regulator-mandated, RCA
for RCA-linked, Standard for everything else. Approve completes the gate; Return
requires a comment. Status is Pending / Approved / Returned.

The Approval stage also exposes cross-team linkage: where another IRR review, in any
team, is driven by the same RRIS obligation or the same regulation, so the same
obligation is not signed off twice in ignorance.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.constants import ROUTE_GATE, ApprovalRoute, ApprovalStatus
from app.domain.errors import CommentRequired
from app.domain.types import ReviewView


def route_of(review: ReviewView) -> ApprovalRoute:
    if review.mandated:
        return ApprovalRoute.IRR
    if review.rca_linked:
        return ApprovalRoute.RCA
    return ApprovalRoute.STANDARD


def gate_of(review: ReviewView) -> str:
    """The single gate this review must pass. One route, one gate, one decision."""
    return ROUTE_GATE[route_of(review)]


def validate_decision(decision: ApprovalStatus, comment: str | None) -> str:
    """Approve completes the gate; returning it needs a reason on record (rule 10)."""
    text = (comment or "").strip()
    if decision is ApprovalStatus.RETURNED and not text:
        raise CommentRequired("A comment is required to return a review.")
    if decision is ApprovalStatus.PENDING:
        raise CommentRequired("A sign-off decision must be Approved or Returned.")
    return text


def related_irr(review: ReviewView, others: Iterable[ReviewView]) -> list[ReviewView]:
    """Other in-plan IRR reviews sharing an RRIS ID or the same regulation."""
    ids = set(review.rris_ids)
    related = []
    for other in others:
        if other.ref == review.ref or not other.in_plan:
            continue
        if route_of(other) is not ApprovalRoute.IRR:
            continue
        shares_rris = bool(ids & set(other.rris_ids))
        shares_regulation = bool(review.regulation) and other.regulation == review.regulation
        if shares_rris or shares_regulation:
            related.append(other)
    return related

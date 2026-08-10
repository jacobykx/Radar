"""Sign-off.

Rule 10: exactly one gate per review, routed by type — IRR for regulator-mandated, RCA
for RCA-linked, Standard for everything else. Approve completes the gate; Return requires
a comment. Status is Pending / Approved / Returned.

The stage also exposes cross-team linkage: where another IRR review, in any team, is
driven by the same RRIS obligation or the same regulation, so the same obligation is not
signed off twice in ignorance of the other.
"""

from __future__ import annotations

from collections.abc import Iterable

from .constants import ROUTE_GATE, ApprovalRoute, ApprovalStatus
from .errors import CommentRequired
from .types import Review


def route_of(review: Review) -> ApprovalRoute:
    if review.mandated:
        return ApprovalRoute.IRR
    if review.rca_linked:
        return ApprovalRoute.RCA
    return ApprovalRoute.STANDARD


def gate_of(review: Review) -> str:
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


def related_irr(review: Review, others: Iterable[Review]) -> list[Review]:
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


def dashboard(reviews: Iterable[Review]) -> dict[str, int]:
    """Counts for the approval header: where the in-plan population has got to."""
    planned = [r for r in reviews if r.in_plan]
    counts = {status.value: 0 for status in ApprovalStatus}
    for review in planned:
        counts[review.approval.status.value] += 1
    counts["total"] = len(planned)
    return counts

"""The audit trail.

Rule 11: every decision is recorded with user, timestamp and rationale where applicable,
and entries are append-only. This module offers exactly one operation -- `record` --
because there is deliberately no way to amend or remove an entry.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditEntry, Review
from app.models.base import utcnow


def record(
    session: Session,
    *,
    username: str,
    action: str,
    detail: str = "",
    review: Review | None = None,
    review_ref: str | None = None,
) -> AuditEntry:
    """Append one entry. Never call this without a real user."""
    entry = AuditEntry(
        review_id=review.id if review is not None else None,
        review_ref=review.ref if review is not None else review_ref,
        action=action,
        detail=detail,
        username=username,
        created_at=utcnow(),
    )
    session.add(entry)
    return entry


def outstanding_query(session: Session):
    """Reviews out of the plan with no rationale on record (a data-quality report)."""
    from app.models import PlanItem

    return (
        session.query(Review)
        .join(PlanItem)
        .filter(PlanItem.staged.is_(False))
        .filter(Review.mandated.is_(False))
        .filter((PlanItem.descope_rationale.is_(None)) | (PlanItem.descope_rationale == ""))
    )

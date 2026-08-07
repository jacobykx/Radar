"""Sign-off (rule 10)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import approval as rules
from app.domain import staging
from app.domain.constants import ApprovalRoute, ApprovalStatus
from app.models import Approval, Review
from app.models.base import utcnow
from app.services import audit, mapping


def ensure_gate(session: Session, review: Review) -> Approval:
    """Exactly one gate per review, created on demand and routed by type."""
    view = mapping.to_view(review)
    route = rules.route_of(view)
    gate = rules.gate_of(view)

    existing = next((a for a in review.approvals if a.gate == gate), None)
    if existing is not None:
        return existing

    # Routing can change if the review is re-classified; the old gate is not carried over.
    for stale in list(review.approvals):
        session.delete(stale)
    review.approvals.clear()

    created = Approval(review_id=review.id, route=route.value, gate=gate,
                       status=ApprovalStatus.PENDING.value)
    session.add(created)
    review.approvals.append(created)
    return created


def decide(
    session: Session,
    review: Review,
    *,
    decision: ApprovalStatus,
    comment: str | None,
    username: str,
) -> Approval:
    """Approve completes the gate; returning it requires a comment."""
    text = rules.validate_decision(decision, comment)
    gate = ensure_gate(session, review)

    gate.status = decision.value
    gate.approver = username
    gate.decided_at = utcnow()
    gate.comment = text or None

    audit.record(
        session, username=username, review=review,
        action=f"{gate.gate} — {'approved' if decision is ApprovalStatus.APPROVED else 'returned'}",
        detail=f"{username}{f': {text}' if text else ''}",
    )
    return gate


def status_of(review: Review) -> ApprovalStatus:
    gate = next(iter(review.approvals), None)
    return ApprovalStatus(gate.status) if gate else ApprovalStatus.PENDING


def dashboard(session: Session, reviews: list[Review], plan_id: int) -> dict:
    """Cards that recalculate to whatever is in the filtered view."""
    views = mapping.views(reviews)
    statuses = [status_of(r) for r in reviews]
    total = len(reviews)
    approved = statuses.count(ApprovalStatus.APPROVED)

    all_views = staging.in_plan(mapping.views(
        session.query(Review).filter(Review.plan_id == plan_id).all()
    ))

    return {
        "total": total,
        "by_status": {
            s.value: statuses.count(s)
            for s in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED, ApprovalStatus.RETURNED)
        },
        "approved_pct": round(approved / total * 100) if total else 0,
        "by_origin": {
            origin: len([v for v in views if v.origin.value == origin])
            for origin in ("Risk Radar inputs", "Risk Assurance", "Regulatory Assurance")
        },
        "by_route": {
            route.value: {
                "total": len([v for v in views if rules.route_of(v) is route]),
                "approved": len([
                    r for r, v in zip(reviews, views, strict=True)
                    if rules.route_of(v) is route and status_of(r) is ApprovalStatus.APPROVED
                ]),
            }
            for route in ApprovalRoute
        },
        "linkage": {
            v.ref: [x.ref for x in rules.related_irr(v, all_views)]
            for v in views
            if rules.route_of(v) is ApprovalRoute.IRR
        },
    }

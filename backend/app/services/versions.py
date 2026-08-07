"""Plan versions (rule 12).

A snapshot captures everything a planner can change: staging, quarters, overrides and
their rationales, sizes and FTE, locations, pre-staging, approvals and steward records.
The audit trail is deliberately not in the snapshot -- restoring a version is a new
audited event, not a rewind of the history.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Approval, PlanVersion, StewardConsultation
from app.models.base import utcnow
from app.services import audit, mapping, planning, prestaging


def _capture(session: Session, plan_id: int) -> dict:
    reviews = planning.all_reviews(session, plan_id)
    w = mapping.current_weights(session, plan_id)
    return {
        "weights": {
            "risk": w.risk, "urgency": w.urgency,
            "coverage_gap": w.coverage_gap, "change": w.change,
        },
        "reviews": {
            r.ref: {
                "effort_size": r.effort_size,
                "fte_override": r.fte_override,
                "business": r.business,
                "locations": [loc.location for loc in sorted(r.locations, key=lambda x: x.sort_order)],
                "item": {
                    "staged": bool(r.item and r.item.staged),
                    "planned_quarter": r.item.planned_quarter if r.item else None,
                    "priority_override": r.item.priority_override if r.item else None,
                    "priority_override_rationale": r.item.priority_override_rationale if r.item else None,
                    "descope_rationale": r.item.descope_rationale if r.item else None,
                },
                "prestaging": {
                    "values": dict((r.prestaging.values if r.prestaging else {}) or {}),
                    "target_start": r.prestaging.target_start.isoformat()
                    if r.prestaging and r.prestaging.target_start
                    else None,
                },
                "approvals": [
                    {"route": a.route, "gate": a.gate, "status": a.status,
                     "approver": a.approver, "comment": a.comment}
                    for a in r.approvals
                ],
                "steward": {
                    "steward_name": r.steward.steward_name,
                    "recorded_by": r.steward.recorded_by,
                } if r.steward else None,
            }
            for r in reviews
        },
    }


def save(session: Session, plan_id: int, *, name: str, note: str, username: str) -> PlanVersion:
    snapshot = _capture(session, plan_id)
    staged = len([v for v in snapshot["reviews"].values() if v["item"]["staged"]])

    version = PlanVersion(
        plan_id=plan_id, name=name.strip() or "Untitled version", note=(note or "").strip(),
        author=username, created_at=utcnow(), staged_count=staged, snapshot=snapshot,
    )
    session.add(version)
    audit.record(session, username=username, action="Version saved",
                 detail=f'"{version.name}" — {staged} staged')
    return version


def restore(session: Session, version: PlanVersion, *, username: str) -> int:
    """Put every captured field back. Reviews absent from the snapshot are left alone."""
    snapshot = version.snapshot or {}
    reviews = {r.ref: r for r in planning.all_reviews(session, version.plan_id)}
    restored = 0

    for ref, data in (snapshot.get("reviews") or {}).items():
        review = reviews.get(ref)
        if review is None:
            continue

        review.effort_size = data["effort_size"]
        review.fte_override = data["fte_override"]
        review.business = data["business"]

        from app.services.reviews import set_locations

        set_locations(session, review, locations=data["locations"],
                      reference=data["locations"], username=username)

        item = review.item
        if item is not None:
            saved = data["item"]
            item.staged = saved["staged"]
            item.planned_quarter = saved["planned_quarter"]
            item.priority_override = saved["priority_override"]
            item.priority_override_rationale = saved["priority_override_rationale"]
            item.descope_rationale = saved["descope_rationale"]
            item.row_version += 1

        record = prestaging.ensure(session, review)
        record.values = dict(data["prestaging"]["values"])
        raw_start = data["prestaging"]["target_start"]
        if raw_start:
            from datetime import date

            record.target_start = date.fromisoformat(raw_start)
        else:
            record.target_start = None

        for stale in list(review.approvals):
            session.delete(stale)
        review.approvals.clear()
        session.flush()
        for saved_gate in data["approvals"]:
            session.add(Approval(review_id=review.id, **saved_gate))

        if data["steward"] is None:
            if review.steward is not None:
                session.delete(review.steward)
                review.steward = None
        else:
            if review.steward is None:
                review.steward = StewardConsultation(
                    review_id=review.id, steward_name=data["steward"]["steward_name"],
                    recorded_by=data["steward"]["recorded_by"], recorded_at=utcnow(),
                )
            else:
                review.steward.steward_name = data["steward"]["steward_name"]
                review.steward.recorded_by = data["steward"]["recorded_by"]

        restored += 1

    weights = snapshot.get("weights")
    if weights:
        from app.domain.types import Weights

        planning.set_weights(session, version.plan_id, Weights(**weights), username)

    audit.record(session, username=username, action="Version restored",
                 detail=f'"{version.name}" — {restored} review(s)')
    return restored

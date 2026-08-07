"""Plan, capacity, scheduling and approval endpoints."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_plan, get_review
from app.api.serialize import review_out, taxonomy_labels
from app.auth.frame import CurrentUser, Role, require
from app.core.db import get_session
from app.domain.constants import SIZE_DAYS, ApprovalStatus
from app.domain.types import Weights
from app.models import Plan, Review
from app.schemas.review import (
    ApprovalPost,
    BulkApprovePost,
    ReviewOut,
    WeightsIn,
    WeightsOut,
)
from app.services import approvals, mapping, planning

router = APIRouter(tags=["plan"])


@router.get("/plan/summary")
def summary(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    return planning.plan_summary(session, plan.id)


@router.get("/plan/weights", response_model=WeightsOut)
def get_weights(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    w = mapping.current_weights(session, plan.id)
    return WeightsOut(risk=w.risk, urgency=w.urgency, coverage_gap=w.coverage_gap, change=w.change)


@router.put("/plan/weights", response_model=WeightsOut)
def put_weights(
    body: WeightsIn,
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    w = Weights(risk=body.risk, urgency=body.urgency, coverage_gap=body.coverage_gap,
                change=body.change)
    planning.set_weights(session, plan.id, w, user.username)
    session.commit()
    return WeightsOut(risk=w.risk, urgency=w.urgency, coverage_gap=w.coverage_gap, change=w.change)


@router.get("/capacity")
def capacity(
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    team: str | None = None,
):
    return planning.capacity_report(session, plan.id, team)


@router.post("/plan/autofill")
def autofill(
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    """Rule 9 -- waterfall Q1->Q4. Anything that will not fit comes back as unplaced."""
    result = planning.autofill(session, plan.id, user.username)
    session.commit()
    return result


@router.post("/plan/clear-quarters")
def clear_quarters(
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    cleared = planning.clear_quarters(session, plan.id, user.username)
    session.commit()
    return {"cleared": cleared}


@router.get("/plan/shaped")
def shaped(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    return planning.shaped_plan(session, plan.id)


@router.get("/plan/export")
def export_plan(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    data = planning.shaped_plan(session, plan.id)
    rows = [["Assurance function", "Ref", "Review", "Mandated", "Size", "Days", "FTE",
             "Quarter", "Business", "Location", "Band"]]
    for group in data["groups"]:
        for r in group["reviews"]:
            rows.append([
                group["function"], r["ref"], r["title"], "Yes" if r["mandated"] else "No",
                r["size"], SIZE_DAYS[r["size"]], r["fte"], r["quarter"] or "",
                r["business"] or "", "; ".join(r["locations"]), r["band"],
            ])
    return _csv_response(rows, f"{plan.year}_IAP_shaped_plan.csv")


# ------------------------------------------------------------------------------ approval


@router.get("/approvals")
def list_approvals(
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    team: str | None = None,
    business: str | None = None,
    location: str | None = None,
    route: str | None = None,
    status: ApprovalStatus | None = None,
):
    reviews = _approval_scope(session, plan.id, team, business, location, route, status)
    weights = mapping.current_weights(session, plan.id)
    taxonomy = taxonomy_labels(session)
    return {
        "dashboard": approvals.dashboard(session, reviews, plan.id),
        "reviews": [review_out(r, weights, taxonomy) for r in reviews],
    }


@router.post("/reviews/{ref}/approval", response_model=ReviewOut)
def decide(
    body: ApprovalPost,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.APPROVER, Role.ADMIN)),
):
    """Rule 10 -- returning a review without a comment is refused."""
    approvals.decide(session, review, decision=body.decision, comment=body.comment,
                     username=user.username)
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.post("/approvals/bulk-approve")
def bulk_approve(
    body: BulkApprovePost,
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.APPROVER, Role.ADMIN)),
):
    """Approve everything matching the supplied filter -- the "approve all in view" action."""
    reviews = _approval_scope(session, plan.id, body.team, body.business, body.location,
                              body.route, body.status)
    for review in reviews:
        approvals.decide(session, review, decision=ApprovalStatus.APPROVED, comment=None,
                         username=user.username)
    session.commit()
    return {"approved": len(reviews), "refs": [r.ref for r in reviews]}


@router.get("/approvals/export")
def export_approvals(
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    team: str | None = None,
    business: str | None = None,
    location: str | None = None,
    route: str | None = None,
    status: ApprovalStatus | None = None,
):
    reviews = _approval_scope(session, plan.id, team, business, location, route, status)
    weights = mapping.current_weights(session, plan.id)
    taxonomy = taxonomy_labels(session)
    linkage = approvals.dashboard(session, reviews, plan.id)["linkage"]

    rows = [["Ref", "Review", "Origin", "Route", "Team", "Sub-team", "Business", "Location",
             "Quarter", "Size", "FTE", "Priority", "Mandated", "Regulator", "Regulation",
             "RRIS IDs", "Risk taxonomy", "Related IRR refs", "Approval status", "Gate",
             "Signed off by", "Signed off on", "Comment"]]
    for review in reviews:
        p = review_out(review, weights, taxonomy)
        gate = next(iter(review.approvals), None)
        rows.append([
            p["ref"], p["title"], p["origin"], p["route"], p["assurance_function"],
            p["sub_team"] or "", p["business"] or "", "; ".join(p["locations"]),
            p["planned_quarter"] or "", p["effort_size"], p["fte"],
            "—" if p["mandated"] else f"{p['effective_priority']:.2f}",
            "Yes" if p["mandated"] else "No", p["regulator"] or "", p["regulation"] or "",
            "; ".join(p["rris_ids"]), p["taxonomy_label"] or "",
            "; ".join(linkage.get(p["ref"], [])), p["approval_status"],
            gate.gate if gate else "", gate.approver if gate else "",
            gate.decided_at.date().isoformat() if gate and gate.decided_at else "",
            gate.comment if gate and gate.comment else "",
        ])
    return _csv_response(rows, f"{plan.year}_IAP_approval_view.csv")


def _approval_scope(
    session: Session, plan_id: int, team, business, location, route, status
) -> list[Review]:
    """Rule 6: descoped reviews are not in the approval population at all."""
    rows = session.query(Review).filter(Review.plan_id == plan_id).order_by(Review.ref).all()
    scope = []
    for review in rows:
        view = mapping.to_view(review)
        if not view.in_plan:
            continue
        if team and view.assurance_function != team:
            continue
        if business and view.business != business:
            continue
        if location and location not in view.locations:
            continue
        approvals.ensure_gate(session, review)
        if route and review.approvals[0].route != route:
            continue
        if status and approvals.status_of(review) is not status:
            continue
        scope.append(review)
    session.flush()
    return scope


def _csv_response(rows: list[list], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

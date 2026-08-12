"""Risk Radar and staging endpoints.

Routers stay thin: parse, delegate to a service, serialise. Every rule lives in
`app.services` / `app.domain` so it cannot be bypassed by reaching a different route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_plan, get_review
from app.api.serialize import review_out, taxonomy_labels
from app.auth.gateway import CurrentUser, Role, get_current_user, require
from app.core.db import get_session
from app.domain.constants import EffortSize, Origin, Quarter, ReferenceKind
from app.models import AssuranceFunction, Plan, Review, ReviewScore, SubTeam
from app.models.base import utcnow
from app.schemas.review import (
    LocationsPut,
    NotePost,
    PriorityOverridePost,
    QuarterPatch,
    ReviewCreate,
    ReviewOut,
    ReviewPatch,
    StagePost,
    StewardPost,
)
from app.services import audit, mapping, reference
from app.services import reviews as review_service

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewOut])
def list_reviews(
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    team: str | None = None,
    sub_team: str | None = None,
    business: str | None = None,
    location: str | None = None,
    origin: Origin | None = None,
    route: str | None = None,
    quarter: Quarter | None = None,
    staged: bool | None = None,
    include_descoped: bool = Query(default=True),
):
    weights = mapping.current_weights(session, plan.id)
    taxonomy = taxonomy_labels(session)
    rows = session.query(Review).filter(Review.plan_id == plan.id).order_by(Review.ref).all()

    out = []
    for review in rows:
        view = mapping.to_view(review)
        if team and view.assurance_function != team:
            continue
        if sub_team and view.sub_team != sub_team:
            continue
        if business and view.business != business:
            continue
        # Rule 13: a location filter matches if *any* of the review's locations match.
        if location and location not in view.locations:
            continue
        if origin and view.origin is not origin:
            continue
        if staged is not None and view.staged != staged:
            continue
        if quarter and view.planned_quarter is not quarter:
            continue
        if not include_descoped and view.descoped:
            continue
        payload = review_out(review, weights, taxonomy)
        if route and payload["route"] != route:
            continue
        out.append(payload)
    return out


@router.get("/{ref}", response_model=ReviewOut)
def get_one(
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
):
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.post("", response_model=ReviewOut, status_code=201)
def create_review(
    body: ReviewCreate,
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    """Both add-forms. Mandated reviews are pinned and always Regulatory Assurance."""
    mandated = body.origin is Origin.REGULATORY
    rationale = review_service.validate_new_review(body.origin, mandated, body.rationale)

    function = (
        session.query(AssuranceFunction)
        .filter(AssuranceFunction.name == body.assurance_function)
        .one()
    )
    sub_team = (
        session.query(SubTeam)
        .filter(SubTeam.assurance_function_id == function.id, SubTeam.name == body.sub_team)
        .one_or_none()
        if body.sub_team
        else None
    )

    ref = _next_ref(session, plan.id)
    review = Review(
        plan_id=plan.id, ref=ref, title=body.title, origin=body.origin.value, mandated=mandated,
        taxonomy_code=body.taxonomy_code, assurance_function_id=function.id,
        sub_team_id=sub_team.id if sub_team else None, business=body.business,
        effort_size=body.effort_size.value, regulator=body.regulator, regulation=body.regulation,
        rris_ids=body.rris_ids, go_live=body.go_live, is_custom=True,
    )
    session.add(review)
    session.flush()

    from app.models import PlanItem

    # Mandated reviews are pinned into the plan; risk-led ones enter the backlog unstaged.
    review.item = PlanItem(review_id=review.id, staged=mandated)
    session.add(
        ReviewScore(review_id=review.id, risk=3, urgency=3, coverage_gap=3, change=3,
                    as_at=utcnow(), source="manual-default")
    )

    if body.locations:
        review_service.set_locations(
            session, review, locations=body.locations,
            reference=reference.labels(session, ReferenceKind.LOCATION), username=user.username,
        )

    review_service.add_note(session, review, text=f"[Rationale] {rationale}",
                            username=user.username)
    audit.record(
        session, username=user.username, review=review, action="Review added",
        detail=f"{body.origin.value} — {body.title} — rationale: {rationale}",
    )
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.patch("/{ref}", response_model=ReviewOut)
def patch_review(
    body: ReviewPatch,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    if body.title is not None:
        review.title = body.title
    if body.effort_size is not None:
        review_service.set_effort(session, review, size=EffortSize(body.effort_size),
                                  username=user.username)
    if "fte_override" in body.model_fields_set:
        review_service.set_fte(session, review, fte=body.fte_override, username=user.username)
    for attr in ("business", "taxonomy_code", "regulator", "regulation", "rris_ids"):
        if attr in body.model_fields_set:
            setattr(review, attr, getattr(body, attr))

    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.put("/{ref}/locations", response_model=ReviewOut)
def put_locations(
    body: LocationsPut,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    review_service.set_locations(
        session, review, locations=body.locations,
        reference=reference.labels(session, ReferenceKind.LOCATION), username=user.username,
    )
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.post("/{ref}/priority-override", response_model=ReviewOut)
def post_override(
    body: PriorityOverridePost,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    """Rule 3 -- a rationale is mandatory; 400 without one."""
    weights = mapping.current_weights(session, plan.id)
    review_service.set_priority_override(
        session, review, value=body.value, rationale=body.rationale,
        username=user.username, weights=weights, row_version=body.row_version,
    )
    session.commit()
    session.refresh(review)
    return review_out(review, weights, taxonomy_labels(session))


@router.delete("/{ref}/priority-override", response_model=ReviewOut)
def delete_override(
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    weights = mapping.current_weights(session, plan.id)
    review_service.clear_priority_override(session, review, username=user.username,
                                           weights=weights)
    session.commit()
    session.refresh(review)
    return review_out(review, weights, taxonomy_labels(session))


@router.post("/{ref}/stage", response_model=ReviewOut)
def post_stage(
    body: StagePost,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    """Rule 6 -- descoping without a rationale is refused (decision D1)."""
    review_service.set_staged(
        session, review, staged=body.staged, rationale=body.rationale,
        username=user.username, row_version=body.row_version,
    )
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.patch("/{ref}/quarter", response_model=ReviewOut)
def patch_quarter(
    body: QuarterPatch,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    review_service.set_quarter(session, review, quarter=body.quarter, username=user.username,
                               row_version=body.row_version)
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.post("/{ref}/steward", response_model=ReviewOut)
def post_steward(
    body: StewardPost,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    """Rule 14 -- record who the steward was, who recorded it and when."""
    review_service.record_steward(session, review, steward_name=body.steward_name,
                                  username=user.username)
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


@router.post("/{ref}/notes", response_model=ReviewOut)
def post_note(
    body: NotePost,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(get_current_user),
):
    review_service.add_note(session, review, text=body.text, username=user.username)
    session.commit()
    session.refresh(review)
    return review_out(review, mapping.current_weights(session, plan.id), taxonomy_labels(session))


def _next_ref(session: Session, plan_id: int) -> str:
    existing = {
        r.ref for r in session.query(Review).filter(Review.plan_id == plan_id).all()
    }
    n = 1
    while f"EXT-{n}" in existing:
        n += 1
    return f"EXT-{n}"

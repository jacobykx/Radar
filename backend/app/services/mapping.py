"""Translate ORM rows into the plain domain views the rules operate on.

Keeping this in one place is what lets `app.domain` stay free of SQLAlchemy, and lets
the methodology be tested without a database.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.domain.constants import EffortSize, Origin, Quarter
from app.domain.types import FunctionCapacity, ReviewView, Scores, Weights
from app.models import AssuranceFunction, PriorityWeight, Review


def to_view(review: Review) -> ReviewView:
    item = review.item
    latest = review.scores[0] if review.scores else None
    return ReviewView(
        ref=review.ref,
        title=review.title,
        origin=Origin(review.origin),
        mandated=review.mandated,
        assurance_function=review.assurance_function.name,
        effort_size=EffortSize(review.effort_size),
        scores=Scores(
            risk=latest.risk,
            urgency=latest.urgency,
            coverage_gap=latest.coverage_gap,
            change=latest.change,
        )
        if latest
        else None,
        sub_team=review.sub_team.name if review.sub_team_id and review.sub_team else None,
        taxonomy_code=review.taxonomy_code,
        business=review.business,
        locations=[loc.location for loc in sorted(review.locations, key=lambda x: x.sort_order)],
        fte_override=review.fte_override,
        rca_linked=review.rca_linked,
        regulator=review.regulator,
        regulation=review.regulation,
        rris_ids=review.rris_list,
        go_live=review.go_live,
        staged=bool(item and item.staged),
        planned_quarter=Quarter(item.planned_quarter)
        if item and item.planned_quarter
        else None,
        priority_override=item.priority_override if item else None,
        descope_rationale=item.descope_rationale if item else None,
    )


def views(reviews: Iterable[Review]) -> list[ReviewView]:
    return [to_view(r) for r in reviews]


def current_weights(session: Session, plan_id: int) -> Weights:
    row = (
        session.query(PriorityWeight)
        .filter(PriorityWeight.plan_id == plan_id)
        .order_by(PriorityWeight.version.desc())
        .first()
    )
    if row is None:
        return Weights()
    return Weights(
        risk=row.a_risk,
        urgency=row.b_urgency,
        coverage_gap=row.c_coverage_gap,
        change=row.d_change,
    )


def capacities(session: Session) -> list[FunctionCapacity]:
    rows = session.query(AssuranceFunction).order_by(AssuranceFunction.name).all()
    return [
        FunctionCapacity(name=r.name, fte_per_quarter=r.fte_per_quarter, is_active=r.is_active)
        for r in rows
    ]

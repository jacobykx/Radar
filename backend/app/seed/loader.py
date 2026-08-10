"""Load the synthetic fixtures into an empty database."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.constants import Origin, ReferenceKind
from app.models import (
    AssuranceFunction,
    Plan,
    PlanItem,
    PriorityWeight,
    ReferenceData,
    Review,
    ReviewLocation,
    ReviewScore,
    SubTeam,
)
from app.models.base import utcnow
from app.seed import data
from app.services import prestaging

SEED_USER = "seed"


def seed(session: Session, *, force: bool = False) -> Plan:
    """Idempotent: returns the existing plan untouched unless `force` is set."""
    existing = session.query(Plan).filter(Plan.year == settings.plan_year).one_or_none()
    if existing is not None and not force:
        return existing

    plan = existing or Plan(
        year=settings.plan_year, name=f"{settings.plan_year} Indicative Annual Plan"
    )
    session.add(plan)
    session.flush()

    _reference(session)
    functions = _functions(session)
    _weights(session, plan)
    _reviews(session, plan, functions)

    session.commit()
    return plan


def _reference(session: Session) -> None:
    def upsert(kind: ReferenceKind, code: str, label: str, order: int) -> None:
        row = (
            session.query(ReferenceData)
            .filter(ReferenceData.kind == kind.value, ReferenceData.code == code)
            .one_or_none()
        )
        if row is None:
            session.add(ReferenceData(kind=kind.value, code=code, label=label,
                                      sort_order=order, active=True))

    for i, (code, label) in enumerate(data.TAXONOMY):
        upsert(ReferenceKind.TAXONOMY, code, label, i)
    for i, name in enumerate(data.BUSINESSES):
        upsert(ReferenceKind.BUSINESS, name, name, i)
    for i, name in enumerate(data.LOCATIONS):
        upsert(ReferenceKind.LOCATION, name, name, i)
    session.flush()


def _functions(session: Session) -> dict[str, AssuranceFunction]:
    out: dict[str, AssuranceFunction] = {}
    for name, fte in data.ASSURANCE_FUNCTIONS.items():
        row = (
            session.query(AssuranceFunction)
            .filter(AssuranceFunction.name == name)
            .one_or_none()
        )
        if row is None:
            row = AssuranceFunction(name=name, fte_per_quarter=fte, is_active=fte > 0)
            session.add(row)
            session.flush()
        out[name] = row

    for function_name, sub_teams in data.SUB_TEAMS.items():
        parent = out[function_name]
        for sub in sub_teams:
            exists = (
                session.query(SubTeam)
                .filter(SubTeam.assurance_function_id == parent.id, SubTeam.name == sub)
                .one_or_none()
            )
            if exists is None:
                session.add(SubTeam(assurance_function_id=parent.id, name=sub))
    session.flush()
    return out


def _weights(session: Session, plan: Plan) -> None:
    exists = session.query(PriorityWeight).filter(PriorityWeight.plan_id == plan.id).first()
    if exists is None:
        session.add(PriorityWeight(plan_id=plan.id, set_by=SEED_USER))
        session.flush()


def _reviews(session: Session, plan: Plan, functions: dict[str, AssuranceFunction]) -> None:
    for spec in data.REVIEWS:
        if session.query(Review).filter(
            Review.plan_id == plan.id, Review.ref == spec["ref"]
        ).one_or_none():
            continue

        mandated = spec.get("mandated", False)
        function = functions[spec["function"]]
        sub_team = (
            session.query(SubTeam)
            .filter(SubTeam.assurance_function_id == function.id,
                    SubTeam.name == spec["sub_team"])
            .one_or_none()
            if spec.get("sub_team")
            else None
        )

        review = Review(
            plan_id=plan.id,
            ref=spec["ref"],
            title=spec["title"],
            # Rule 4: mandated implies Regulatory Assurance; seeded candidates come
            # from the radar.
            origin=(Origin.REGULATORY if mandated else Origin.RADAR).value,
            mandated=mandated,
            taxonomy_code=spec["taxonomy"],
            assurance_function_id=function.id,
            sub_team_id=sub_team.id if sub_team else None,
            business=spec.get("business"),
            effort_size=spec["size"].value,
            regulator=spec.get("regulator"),
            regulation=spec.get("regulation"),
            rris_ids=spec.get("rris_ids"),
            rca_linked=spec["ref"] in data.RCA_LINKED,
            go_live=spec.get("go_live"),
        )
        session.add(review)
        session.flush()

        risk, urgency, coverage_gap, change = spec["scores"]
        session.add(ReviewScore(review_id=review.id, risk=risk, urgency=urgency,
                                coverage_gap=coverage_gap, change=change,
                                as_at=utcnow(), source="scoring-engine (synthetic)"))

        for i, location in enumerate(spec.get("locations", [])):
            session.add(ReviewLocation(review_id=review.id, location=location, sort_order=i))

        # Rule 5: mandated reviews are pinned into the plan, in their go-live quarter.
        quarter = None
        if mandated and spec.get("go_live"):
            quarter = f"Q{(spec['go_live'].month - 1) // 3 + 1}"
        session.add(PlanItem(review_id=review.id, staged=mandated, planned_quarter=quarter))
        session.flush()

        prestaging.ensure(session, review)

    session.flush()

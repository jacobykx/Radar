"""Plan-level operations: weights, capacity, waterfall auto-fill and the shaped plan."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import capacity as cap
from app.domain import scheduling, scoring, staging
from app.domain.constants import QUARTERS
from app.domain.types import Weights
from app.models import PriorityWeight, Review
from app.services import audit, mapping


def all_reviews(session: Session, plan_id: int) -> list[Review]:
    return session.query(Review).filter(Review.plan_id == plan_id).order_by(Review.ref).all()


def set_weights(session: Session, plan_id: int, weights: Weights, username: str) -> Weights:
    latest = (
        session.query(PriorityWeight)
        .filter(PriorityWeight.plan_id == plan_id)
        .order_by(PriorityWeight.version.desc())
        .first()
    )
    version = (latest.version + 1) if latest else 1
    session.add(
        PriorityWeight(
            plan_id=plan_id,
            a_risk=weights.risk,
            b_urgency=weights.urgency,
            c_coverage_gap=weights.coverage_gap,
            d_change=weights.change,
            version=version,
            set_by=username,
        )
    )
    audit.record(
        session, username=username, action="Priority weights changed",
        detail=(
            f"risk {weights.risk}, urgency {weights.urgency}, "
            f"coverage {weights.coverage_gap}, change {weights.change} (v{version})"
        ),
    )
    return weights


def capacity_report(session: Session, plan_id: int, team: str | None = None) -> dict:
    """Capacity for the selected scope.

    Two granularities, deliberately. `aggregate` is the roll-up the staging screen
    shows; `functions` is the per-function detail, which is the granularity the
    waterfall actually enforces against -- a function's spare FTE cannot cover another's.
    """
    everything = mapping.views(all_reviews(session, plan_id))
    reviews = [r for r in everything if not team or r.assurance_function == team]
    capacities = [
        c for c in mapping.capacities(session) if c.is_active and (not team or c.name == team)
    ]
    fill = cap.bottom_up_fill(reviews, capacities)

    fte_per_quarter = sum(c.fte_per_quarter for c in capacities)
    in_scope = [r for r in reviews if not r.descoped]
    planned = [r for r in reviews if r.in_plan]
    aggregate = [
        {
            "quarter": q.value,
            "capacity": fte_per_quarter,
            "demand": sum(r.fte for r in planned if r.planned_quarter is q),
        }
        for q in QUARTERS
    ]
    for row in aggregate:
        row["over"] = row["demand"] > row["capacity"]
        row["warn"] = not row["over"] and row["demand"] > row["capacity"] * 0.85

    functions = []
    for capacity in capacities:
        load = cap.function_load(reviews, capacity)
        functions.append(
            {
                "function": load.function,
                "fte_per_quarter": load.fte_per_quarter,
                "quarters": [
                    {
                        "quarter": q.quarter.value,
                        "capacity": q.capacity,
                        "demand": q.demand,
                        "headroom": q.headroom,
                        "over": q.over,
                    }
                    for q in load.quarters
                ],
                "unscheduled_fte": load.unscheduled_fte,
                "over": load.over,
            }
        )

    return {
        "scope": {
            "label": team or "Portfolio (all teams)",
            "candidate_reviews": len(in_scope),
            "fte_per_quarter": fte_per_quarter,
            "annual_fte_quarters": fill.annual_fte_quarters,
        },
        "bottom_up": {
            "annual_fte_quarters": fill.annual_fte_quarters,
            "mandated_fte": fill.mandated_fte,
            "additional_fte": fill.additional_fte,
            "remaining_after_mandated": fill.remaining_after_mandated,
            "headroom": fill.headroom,
            "over": fill.over,
        },
        "aggregate": aggregate,
        "unscheduled_count": len([r for r in planned if r.planned_quarter is None]),
        "functions": functions,
    }


def autofill(session: Session, plan_id: int, username: str) -> dict:
    """Rule 9: waterfall Q1->Q4 and persist the result, reporting what would not fit."""
    reviews = all_reviews(session, plan_id)
    by_ref = {r.ref: r for r in reviews}
    weights = mapping.current_weights(session, plan_id)

    result = scheduling.waterfall(
        mapping.views(reviews), mapping.capacities(session), weights
    )

    for ref, quarter in result.quarters.items():
        review = by_ref[ref]
        if review.item is None:
            continue
        review.item.planned_quarter = quarter.value if quarter else None
        review.item.row_version += 1

    audit.record(session, username=username, action="Quarters auto-filled",
                 detail=result.summary)

    return {
        "placed": [
            {"ref": p.ref, "function": p.function,
             "quarter": p.quarter.value if p.quarter else None, "fte": p.fte, "moved": p.moved}
            for p in result.placed
        ],
        "unplaced": [
            {"ref": p.ref, "function": p.function, "quarter": None, "fte": p.fte, "moved": False}
            for p in result.unplaced
        ],
        "summary": result.summary,
    }


def clear_quarters(session: Session, plan_id: int, username: str) -> int:
    cleared = 0
    for review in all_reviews(session, plan_id):
        if review.item and review.item.planned_quarter:
            review.item.planned_quarter = None
            review.item.row_version += 1
            cleared += 1
    audit.record(session, username=username, action="Quarters cleared",
                 detail=f"{cleared} review(s) unscheduled")
    return cleared


def shaped_plan(session: Session, plan_id: int) -> dict:
    """The Gantt: in-plan reviews grouped by assurance function, laid out by quarter."""
    reviews = all_reviews(session, plan_id)
    weights = mapping.current_weights(session, plan_id)
    planned = staging.in_plan(mapping.views(reviews))

    groups: dict[str, list] = {}
    for view in sorted(planned, key=lambda v: scoring.sort_key(v, weights)):
        groups.setdefault(view.assurance_function, []).append(view)

    return {
        "quarters": [q.value for q in QUARTERS],
        "groups": [
            {
                "function": name,
                "total_fte": sum(v.fte for v in items),
                "by_quarter": {
                    q.value: sum(v.fte for v in items if v.planned_quarter is q) for q in QUARTERS
                },
                "reviews": [
                    {
                        "ref": v.ref,
                        "title": v.title,
                        "mandated": v.mandated,
                        "size": v.effort_size.value,
                        "fte": v.fte,
                        "business": v.business,
                        "locations": v.locations,
                        "quarter": v.planned_quarter.value if v.planned_quarter else None,
                        "band": scoring.band_of(v, weights).value,
                    }
                    for v in items
                ],
            }
            for name, items in groups.items()
        ],
    }


def plan_summary(session: Session, plan_id: int) -> dict:
    """The funnel and headline numbers on the dashboard strip."""
    views = mapping.views(all_reviews(session, plan_id))
    planned = staging.in_plan(views)
    capacities = [c for c in mapping.capacities(session) if c.is_active]
    annual = sum(c.annual_fte_quarters for c in capacities)
    used = sum(v.fte for v in planned)

    return {
        "candidates": len(views),
        "in_scope": len(planned),
        "descoped": len(staging.descoped(views)),
        "scheduled": len([v for v in planned if v.planned_quarter]),
        "unscheduled": len([v for v in planned if not v.planned_quarter]),
        "outstanding_rationales": len(staging.outstanding_rationales(views)),
        "annual_fte_quarters": annual,
        "used_fte": used,
        "utilisation_pct": round(used / annual * 100) if annual else 0,
        "fte_by_quarter": {
            q.value: sum(v.fte for v in planned if v.planned_quarter is q) for q in QUARTERS
        },
    }

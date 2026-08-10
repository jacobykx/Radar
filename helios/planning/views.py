"""JSON views of the plan.

The UI renders whatever these return and computes nothing itself, so a rule can only ever
be implemented once. Every derived number a screen shows — priority, band, FTE, headroom,
readiness — is worked out here.
"""

from __future__ import annotations

from . import approval, capacity, prestaging, scoring, staging
from .constants import DRIVERS, QUARTERS, SIZE_DAYS, SIZE_FTE, EffortSize
from .seed import SUB_TEAMS
from .store import Plan


def review(plan: Plan, item, *, related: bool = False) -> dict:
    """One review, with every derived value the screens need."""
    weights = plan.weights
    effective = scoring.effective_priority(item, weights)
    computed = (
        scoring.computed_priority(item.scores, weights)
        if item.scores and not item.mandated
        else None
    )
    record = prestaging.read(item)

    out = {
        "ref": item.ref,
        "title": item.title,
        "assurance_function": item.assurance_function,
        "sub_team": item.sub_team,
        "origin": item.origin.value,
        "mandated": item.mandated,
        "taxonomy_code": item.taxonomy_code,
        "taxonomy_label": taxonomy_label(plan, item.taxonomy_code),
        "business": item.business,
        "locations": list(item.locations),
        "effort_size": item.effort_size.value,
        "effort_days": item.effort_days,
        "fte": item.fte,
        "fte_override": item.fte_override,
        "scores": item.scores.to_dict() if item.scores else None,
        "seeded_scores": item.seeded_scores.to_dict() if item.seeded_scores else None,
        "scores_edited": sorted(
            k for k in ("risk", "urgency", "coverage_gap", "change")
            if item.seeded_scores and getattr(item.scores, k) != getattr(item.seeded_scores, k)
        ) if item.seeded_scores and item.scores else [],
        "computed_priority": round(computed, 2) if computed is not None else None,
        "effective_priority": round(effective, 2) if effective is not None else None,
        "priority_override": item.priority_override,
        "priority_rationale": item.priority_rationale,
        "band": scoring.band_of(item, weights).value,
        "staged": item.staged,
        "descoped": item.descoped,
        "in_plan": item.in_plan,
        "rationale_outstanding": item.rationale_outstanding,
        "descope_rationale": item.descope_rationale,
        "planned_quarter": item.planned_quarter.value if item.planned_quarter else None,
        "go_live": item.go_live.isoformat() if item.go_live else None,
        "regulator": item.regulator,
        "regulation": item.regulation,
        "rris_ids": list(item.rris_ids),
        "rca_linked": item.rca_linked,
        "steward_consulted": item.steward_consulted,
        "steward_name": item.steward_name,
        "comments": [c.to_dict() for c in item.comments],
        "comment_count": len(item.comments),
        "taxonomy_short": taxonomy_short(plan, item.taxonomy_code),
        "function_short": function_short(item.assurance_function),
        "route": approval.route_of(item).value,
        "gate": approval.gate_of(item),
        "approval": item.approval.to_dict(),
        "helios_complete": record["complete"],
        "helios_missing": len(record["errors"]),
    }
    if related:
        out["related_irr"] = [r.ref for r in approval.related_irr(item, plan.reviews)]
    return out


#: Column-width abbreviations, as the prototype's dense table uses. The full value stays
#: on the element's title so nothing is actually lost.
_TAXONOMY_SHORT = {
    "change-ai": "Change/AI", "op-res": "Op Res & TP", "prudential": "Prudential",
    "fincrime": "Fin Crime", "conduct": "Conduct",
}


def taxonomy_short(plan: Plan, code: str) -> str:
    return _TAXONOMY_SHORT.get(code) or taxonomy_label(plan, code)


def function_short(name: str) -> str:
    return (name.removesuffix(" Assurance")
            .replace("Regulatory ", "Reg ")
            .replace("Wholesale Credit Risk Unit", "Wholesale Credit"))


def taxonomy_label(plan: Plan, code: str) -> str:
    for entry in plan.reference.get("taxonomy", []):
        if entry.get("code") == code:
            return entry.get("label", code)
    return code


def stats(plan: Plan) -> dict:
    """The header funnel and the numbers that tell a planner where the plan stands."""
    reviews = plan.reviews
    in_plan = staging.in_plan(reviews)
    fill = capacity.bottom_up_fill(reviews, plan.capacities)
    scheduled = [r for r in in_plan if r.planned_quarter]
    ready = [r for r in in_plan if prestaging.read(r)["complete"]]
    approved = [r for r in in_plan if r.approval.status.value == "Approved"]

    quarter_fte = {
        q.value: sum(r.fte for r in in_plan if r.planned_quarter == q) for q in QUARTERS
    }
    per_quarter_capacity = sum(c.fte_per_quarter for c in plan.capacities if c.is_active)

    return {
        "candidates": len(reviews),
        "in_plan": len(in_plan),
        "descoped": len(staging.descoped(reviews)),
        "outstanding_rationales": len(staging.outstanding_rationales(reviews)),
        "scheduled": len(scheduled),
        "unscheduled": len(in_plan) - len(scheduled),
        "helios_ready": len(ready),
        "approved": len(approved),
        "mandated": len([r for r in in_plan if r.mandated]),
        "fill": fill.to_dict(),
        "utilisation": (
            round(100 * (fill.mandated_fte + fill.additional_fte) / fill.annual_fte_quarters)
            if fill.annual_fte_quarters else 0
        ),
        "quarter_fte": quarter_fte,
        "quarter_capacity": per_quarter_capacity,
    }


def capacity_view(plan: Plan) -> dict:
    loads = [
        capacity.function_load(plan.reviews, c).to_dict()
        for c in plan.capacities
        if c.is_active
    ]
    return {
        "fill": capacity.bottom_up_fill(plan.reviews, plan.capacities).to_dict(),
        "functions": loads,
    }


def shaped_plan(plan: Plan) -> list[dict]:
    """The in-plan population grouped by risk taxonomy, priority order within each."""
    in_plan = sorted(staging.in_plan(plan.reviews),
                     key=lambda r: scoring.sort_key(r, plan.weights))
    groups: dict[str, dict] = {}
    for item in in_plan:
        code = item.taxonomy_code or "—"
        group = groups.setdefault(code, {
            "code": code,
            "label": taxonomy_label(plan, code),
            "reviews": [],
            "fte": 0,
        })
        group["reviews"].append(review(plan, item))
        group["fte"] += item.fte
    return list(groups.values())


def options(plan: Plan) -> dict:
    """Everything the UI needs to build its selects, so it hard-codes no list."""
    return {
        "quarters": [q.value for q in QUARTERS],
        "sizes": [{"value": s.value, "days": SIZE_DAYS[s], "fte": SIZE_FTE[s]}
                  for s in EffortSize],
        "functions": [{"name": c.name, "fte_per_quarter": c.fte_per_quarter,
                       "active": c.is_active} for c in plan.capacities],
        "sub_teams": {k: list(v) for k, v in SUB_TEAMS.items()},
        "drivers": [{"key": k, "label": label} for k, label in DRIVERS],
        "reference": plan.reference,
        "businesses": plan.reference.get("business", []),
        "locations": plan.reference.get("location", []),
        "taxonomy": plan.reference.get("taxonomy", []),
    }


def whole(plan: Plan) -> dict:
    """One payload for the whole screen. The UI fetches this after every change."""
    return {
        "year": plan.year,
        "weights": plan.weights.to_dict(),
        "reviews": [review(plan, r, related=True) for r in plan.reviews],
        "stats": stats(plan),
        "capacity": capacity_view(plan),
        "shaped": shaped_plan(plan),
        "approval": approval.dashboard(plan.reviews),
        "versions": [v.summary() for v in reversed(plan.versions)],
        "audit": [a.to_dict() for a in plan.audit],
        "options": options(plan),
    }

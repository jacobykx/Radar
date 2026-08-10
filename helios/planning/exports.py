"""The governance CSVs: the shaped plan, the approval view, and the audit trail.

The Helios upload is not the only file this produces — the plan and the approval view are
what goes into an L2 pre-read, and the audit trail is what answers "who decided that, and
why". They share `helios.export.table`, so every file the tool emits opens the same way.
"""

from __future__ import annotations

from .. import export
from . import approval, prestaging, scoring, staging, views
from .store import Plan

PLAN_HEADER = [
    "Ref", "Review", "Risk taxonomy", "Origin", "Mandated", "Assurance function", "Sub-team",
    "Business", "Location(s)", "Planned quarter", "Go-live", "Effort size", "Effort days", "FTE",
    "Risk score", "Urgency index", "Coverage gap", "Change index",
    "Computed priority", "Priority override", "Override rationale", "Effective priority", "Band",
    "Approval route", "Approval status", "Helios ready",
]

APPROVAL_HEADER = [
    "Ref", "Review", "Assurance function", "Sub-team", "Business", "Location(s)",
    "Planned quarter", "Effort size", "FTE", "Priority", "Band", "Mandated",
    "Regulator", "Regulation", "RRIS ID(s)", "Related IRR reviews",
    "Route", "Gate", "Status", "Signed off by", "Signed off at", "Note",
]

AUDIT_HEADER = ["Timestamp", "User", "Ref", "Action", "Detail"]


def plan_csv(plan: Plan) -> str:
    """The shaped plan, priority order, mandated first."""
    rows = []
    for item in sorted(staging.in_plan(plan.reviews),
                       key=lambda r: scoring.sort_key(r, plan.weights)):
        scores = item.scores
        computed = (
            scoring.computed_priority(scores, plan.weights)
            if scores and not item.mandated else None
        )
        effective = scoring.effective_priority(item, plan.weights)
        rows.append([
            item.ref, item.title, views.taxonomy_label(plan, item.taxonomy_code),
            item.origin.value, "Yes" if item.mandated else "No",
            item.assurance_function, item.sub_team, item.business, "; ".join(item.locations),
            item.planned_quarter.value if item.planned_quarter else "",
            item.go_live.isoformat() if item.go_live else "",
            item.effort_size.value, item.effort_days, item.fte,
            _num(scores.risk if scores and not item.mandated else None),
            _num(scores.urgency if scores and not item.mandated else None),
            _num(scores.coverage_gap if scores and not item.mandated else None),
            _num(scores.change if scores and not item.mandated else None),
            _num(computed), _num(item.priority_override), item.priority_rationale,
            _num(effective), scoring.band_of(item, plan.weights).value,
            approval.route_of(item).value, item.approval.status.value,
            "Yes" if prestaging.read(item)["complete"] else "No",
        ])
    return export.table(PLAN_HEADER, rows)


def approval_csv(plan: Plan) -> str:
    """The approval view: what each gate is being asked to sign, and what it decided."""
    rows = []
    for item in sorted(staging.in_plan(plan.reviews),
                       key=lambda r: scoring.sort_key(r, plan.weights)):
        related = approval.related_irr(item, plan.reviews)
        rows.append([
            item.ref, item.title, item.assurance_function, item.sub_team, item.business,
            "; ".join(item.locations),
            item.planned_quarter.value if item.planned_quarter else "",
            item.effort_size.value, item.fte,
            _num(scoring.effective_priority(item, plan.weights)),
            scoring.band_of(item, plan.weights).value, "Yes" if item.mandated else "No",
            item.regulator, item.regulation, "; ".join(item.rris_ids),
            "; ".join(r.ref for r in related),
            approval.route_of(item).value, approval.gate_of(item),
            item.approval.status.value, item.approval.by, item.approval.at, item.approval.note,
        ])
    return export.table(APPROVAL_HEADER, rows)


def audit_csv(plan: Plan) -> str:
    """Oldest first — the order it is read in, which is the reverse of how it is shown."""
    rows = [[a.at, a.user, a.ref, a.action, a.detail] for a in reversed(plan.audit)]
    return export.table(AUDIT_HEADER, rows)


def helios_rows(plan: Plan) -> list[dict[str, str]]:
    """The in-plan population as Helios rows, in the order the plan is shaped."""
    ordered = sorted(staging.in_plan(plan.reviews),
                     key=lambda r: scoring.sort_key(r, plan.weights))
    return prestaging.rows(ordered)


def _num(value: float | None) -> str:
    """Two decimals, or empty. Never `None` and never a bare float in a CSV cell."""
    return "" if value is None else f"{value:.2f}"

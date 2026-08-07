"""ORM -> response payloads."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import approval as approval_rules
from app.domain import scoring
from app.domain.constants import SIZE_DAYS, ReferenceKind
from app.domain.types import Weights
from app.models import Review
from app.services import approvals, mapping


def taxonomy_labels(session: Session) -> dict[str, str]:
    from app.models import ReferenceData

    rows = (
        session.query(ReferenceData)
        .filter(ReferenceData.kind == ReferenceKind.TAXONOMY.value)
        .all()
    )
    return {r.code: r.label for r in rows}


def review_out(
    review: Review, weights: Weights, taxonomy: dict[str, str] | None = None
) -> dict:
    view = mapping.to_view(review)
    item = review.item
    latest = review.scores[0] if review.scores else None
    taxonomy = taxonomy or {}

    computed = (
        scoring.computed_priority(view.scores, weights)
        if view.scores is not None and not view.mandated
        else None
    )

    return {
        "ref": view.ref,
        "title": view.title,
        "origin": view.origin,
        "mandated": view.mandated,
        "taxonomy_code": view.taxonomy_code,
        "taxonomy_label": taxonomy.get(view.taxonomy_code or "", view.taxonomy_code),
        "assurance_function": view.assurance_function,
        "sub_team": view.sub_team,
        "business": view.business,
        "locations": view.locations,
        "effort_size": view.effort_size,
        "effort_days": SIZE_DAYS[view.effort_size],
        "fte": view.fte,
        "fte_override": view.fte_override,
        "regulator": view.regulator,
        "regulation": view.regulation,
        "rris_ids": view.rris_ids,
        "rca_linked": view.rca_linked,
        "go_live": view.go_live,
        "scores": {
            "risk": latest.risk,
            "urgency": latest.urgency,
            "coverage_gap": latest.coverage_gap,
            "change": latest.change,
            "as_at": latest.as_at,
            "source": latest.source,
        }
        if latest
        else None,
        "computed_priority": computed,
        "priority_override": view.priority_override,
        "priority_override_rationale": item.priority_override_rationale if item else None,
        "effective_priority": scoring.effective_priority(view, weights),
        "band": scoring.band_of(view, weights),
        "staged": view.staged,
        "descoped": view.descoped,
        "rationale_outstanding": view.rationale_outstanding,
        "descope_rationale": view.descope_rationale,
        "planned_quarter": view.planned_quarter,
        "row_version": item.row_version if item else 1,
        "route": approval_rules.route_of(view).value,
        "approval_status": approvals.status_of(review),
        "steward": {
            "steward_name": review.steward.steward_name,
            "recorded_by": review.steward.recorded_by,
            "recorded_at": review.steward.recorded_at,
        }
        if review.steward
        else None,
        "notes": [
            {"author": n.author, "text": n.text, "created_at": n.created_at}
            for n in review.notes
        ],
    }

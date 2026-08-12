"""Pre-staging, versions, audit trail and reference data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_plan, get_review
from app.api.plan import _csv_response
from app.auth.gateway import CurrentUser, Role, require
from app.core.db import get_session
from app.domain import helios
from app.domain.constants import ReferenceKind
from app.models import AuditEntry, Plan, PlanVersion, Review
from app.schemas.review import (
    AuditOut,
    PrestagingPatch,
    ReferencePut,
    VersionOut,
    VersionPost,
)
from app.services import audit as audit_service
from app.services import mapping, prestaging, reference, versions

router = APIRouter(tags=["governance"])


# --------------------------------------------------------------------------- pre-staging


@router.get("/prestaging/spec")
def prestaging_spec(session: Session = Depends(get_session)):
    """The field set, so the frontend renders the spec rather than a hard-coded copy."""
    return {
        "fields": [
            {
                "key": f.key, "label": f.label, "type": f.type, "group": f.group.value,
                "allowed": list(f.allowed) if f.allowed else None,
                "hint": f.hint, "full_width": f.full_width,
                "required": f.key in helios.REQUIRED_FIELDS,
            }
            for f in helios.HELIOS_FIELDS
        ],
        "business": reference.labels(session, ReferenceKind.BUSINESS),
        "location": reference.labels(session, ReferenceKind.LOCATION),
    }


@router.get("/prestaging")
def list_prestaging(
    session: Session = Depends(get_session), plan: Plan = Depends(get_plan),
    team: str | None = None,
):
    out = []
    for review in _in_plan(session, plan.id, team):
        out.append(prestaging.read(session, review))
    session.commit()
    return out


@router.patch("/prestaging/{ref}")
def patch_prestaging(
    body: PrestagingPatch,
    review: Review = Depends(get_review),
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    """Derived fields are ignored on write -- they follow Target Start Date, nothing else."""
    prestaging.update(session, review, changes=body.changes, username=user.username)
    session.commit()
    session.refresh(review)
    return prestaging.read(session, review)


@router.get("/prestaging/export")
def export_prestaging(
    session: Session = Depends(get_session), plan: Plan = Depends(get_plan),
    team: str | None = None,
):
    rows = prestaging.export_rows(session, _in_plan(session, plan.id, team))
    session.commit()
    return _csv_response(rows, f"{plan.year}_IAP_Helios_prestaging.csv")


# ------------------------------------------------------------------------------ versions


@router.get("/versions", response_model=list[VersionOut])
def list_versions(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    return (
        session.query(PlanVersion)
        .filter(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.created_at.desc())
        .all()
    )


@router.post("/versions", response_model=VersionOut, status_code=201)
def save_version(
    body: VersionPost,
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.PLANNER, Role.ADMIN)),
):
    version = versions.save(session, plan.id, name=body.name, note=body.note,
                            username=user.username)
    session.commit()
    session.refresh(version)
    return version


@router.post("/versions/{version_id}/restore")
def restore_version(
    version_id: int,
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.ADMIN, Role.PLANNER)),
):
    version = session.get(PlanVersion, version_id)
    if version is None or version.plan_id != plan.id:
        raise HTTPException(status_code=404, detail="No such version.")
    restored = versions.restore(session, version, username=user.username)
    session.commit()
    return {"restored": restored, "name": version.name}


@router.delete("/versions/{version_id}", status_code=204)
def delete_version(
    version_id: int,
    session: Session = Depends(get_session),
    plan: Plan = Depends(get_plan),
    user: CurrentUser = Depends(require(Role.ADMIN)),
):
    version = session.get(PlanVersion, version_id)
    if version is None or version.plan_id != plan.id:
        raise HTTPException(status_code=404, detail="No such version.")
    audit_service.record(session, username=user.username, action="Version deleted",
                         detail=f'"{version.name}"')
    session.delete(version)
    session.commit()


# --------------------------------------------------------------------------------- audit
# Append-only (rule 11): read and export only. There is deliberately no PATCH or DELETE.


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    session: Session = Depends(get_session), ref: str | None = None, limit: int = 500
):
    query = session.query(AuditEntry).order_by(AuditEntry.created_at.desc())
    if ref:
        query = query.filter(AuditEntry.review_ref == ref)
    return query.limit(limit).all()


@router.get("/audit/outstanding")
def outstanding(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    """Reviews out of the plan with no rationale on record."""
    weights = mapping.current_weights(session, plan.id)
    from app.domain import scoring

    rows = audit_service.outstanding_query(session).filter(Review.plan_id == plan.id).all()
    return [
        {
            "ref": r.ref,
            "title": r.title,
            "assurance_function": mapping.to_view(r).assurance_function,
            "effective_priority": scoring.effective_priority(mapping.to_view(r), weights),
        }
        for r in rows
    ]


@router.get("/audit/export")
def export_audit(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    entries = session.query(AuditEntry).order_by(AuditEntry.created_at.desc()).all()
    rows = [["When", "Who", "Ref", "Action", "Detail"]]
    rows += [
        [e.created_at.isoformat(), e.username, e.review_ref or "—", e.action, e.detail]
        for e in entries
    ]
    return _csv_response(rows, f"{plan.year}_IAP_audit_trail.csv")


# ------------------------------------------------------------------------ reference data


@router.get("/reference-data")
def get_reference(session: Session = Depends(get_session)):
    return {
        "taxonomy": [
            {"code": r.code, "label": r.label}
            for r in reference.values(session, ReferenceKind.TAXONOMY)
        ],
        "business": [
            {"code": r.code, "label": r.label}
            for r in reference.values(session, ReferenceKind.BUSINESS)
        ],
        "location": [
            {"code": r.code, "label": r.label}
            for r in reference.values(session, ReferenceKind.LOCATION)
        ],
        "source": "kbd" if reference.fetch_from_kbd() else "local",
    }


@router.put("/reference-data")
def put_reference(
    body: ReferencePut,
    session: Session = Depends(get_session),
    user: CurrentUser = Depends(require(Role.ADMIN)),
):
    for kind, entries in (
        (ReferenceKind.TAXONOMY, body.taxonomy),
        (ReferenceKind.BUSINESS, body.business),
        (ReferenceKind.LOCATION, body.location),
    ):
        if entries is not None:
            reference.replace(session, kind, [e.model_dump() for e in entries], user.username)
    session.commit()
    return get_reference(session)


@router.get("/reference-data/impact")
def reference_impact(session: Session = Depends(get_session), plan: Plan = Depends(get_plan)):
    """Values still carried by reviews but no longer in the lists (risk R1)."""
    return reference.impact(session, plan.id)


def _in_plan(session: Session, plan_id: int, team: str | None) -> list[Review]:
    rows = session.query(Review).filter(Review.plan_id == plan_id).order_by(Review.ref).all()
    out = []
    for review in rows:
        view = mapping.to_view(review)
        if not view.in_plan:
            continue
        if team and view.assurance_function != team:
            continue
        out.append(review)
    return out

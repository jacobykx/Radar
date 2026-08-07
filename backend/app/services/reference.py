"""Reference data.

In production these lists come from the Helios KBD reference-data mapper; this service
is the seam. `fetch_from_kbd` is where that call goes -- until it exists, the admin
screen behind these endpoints is the fallback, exactly as the brief specifies.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.constants import ReferenceKind
from app.models import ReferenceData, Review, ReviewLocation
from app.services import audit


def values(session: Session, kind: ReferenceKind, *, active_only: bool = True) -> list[ReferenceData]:
    query = session.query(ReferenceData).filter(ReferenceData.kind == kind.value)
    if active_only:
        query = query.filter(ReferenceData.active.is_(True))
    return query.order_by(ReferenceData.sort_order, ReferenceData.label).all()


def labels(session: Session, kind: ReferenceKind) -> list[str]:
    return [r.label for r in values(session, kind)]


def replace(
    session: Session, kind: ReferenceKind, entries: list[dict], username: str
) -> list[ReferenceData]:
    """Replace a list. Values still in use are deactivated, never deleted (risk R1)."""
    incoming = {e["code"]: e.get("label") or e["code"] for e in entries}
    existing = {r.code: r for r in values(session, kind, active_only=False)}

    for order, (code, label) in enumerate(incoming.items()):
        row = existing.get(code)
        if row is None:
            session.add(ReferenceData(kind=kind.value, code=code, label=label,
                                      sort_order=order, active=True))
        else:
            row.label, row.sort_order, row.active = label, order, True

    for code, row in existing.items():
        if code not in incoming:
            row.active = False

    audit.record(session, username=username, action="Reference data updated",
                 detail=f"{kind.value}: {len(incoming)} value(s)")
    return values(session, kind)


def impact(session: Session, plan_id: int) -> dict:
    """Values still carried by reviews that are no longer in the reference lists."""
    taxonomy = {r.code for r in values(session, ReferenceKind.TAXONOMY)}
    businesses = set(labels(session, ReferenceKind.BUSINESS))
    locations = set(labels(session, ReferenceKind.LOCATION))

    reviews = session.query(Review).filter(Review.plan_id == plan_id).all()
    used_locations = {
        loc.location
        for loc in session.query(ReviewLocation)
        .join(Review)
        .filter(Review.plan_id == plan_id)
        .all()
    }

    return {
        "taxonomy": sorted(
            {r.taxonomy_code for r in reviews if r.taxonomy_code and r.taxonomy_code not in taxonomy}
        ),
        "business": sorted(
            {r.business for r in reviews if r.business and r.business not in businesses}
        ),
        "location": sorted(used_locations - locations),
    }


def fetch_from_kbd() -> dict | None:
    """Integration seam for the Helios KBD reference-data mapper (IAP-24).

    Returns None until the feed is wired, which is what makes the admin screen the
    fallback rather than the source of truth.
    """
    return None

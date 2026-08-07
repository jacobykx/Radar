"""Review-level operations: staging, descoping, overrides, locations, stewards.

Every rule is enforced here rather than in the router, so it holds for any caller, and
every state change writes an audit entry in the same transaction as the change itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.domain import scoring, staging
from app.domain.constants import EffortSize, Origin, Quarter
from app.domain.errors import StaleWrite
from app.models import PlanItem, Review, ReviewLocation, ReviewNote, StewardConsultation
from app.models.base import utcnow
from app.services import audit, mapping


def get_by_ref(session: Session, plan_id: int, ref: str) -> Review | None:
    return (
        session.query(Review).filter(Review.plan_id == plan_id, Review.ref == ref).one_or_none()
    )


def _item(review: Review) -> PlanItem:
    if review.item is None:
        review.item = PlanItem(review_id=review.id, staged=False)
    return review.item


def _check_version(item: PlanItem, expected: int | None) -> None:
    """Optimistic concurrency (risk R2): refuse a write made against stale state."""
    if expected is not None and expected != item.row_version:
        raise StaleWrite(
            f"This review changed since you loaded it (version {item.row_version}, you sent "
            f"{expected}). Reload and try again."
        )


def _touch(item: PlanItem) -> None:
    item.row_version += 1


def set_staged(
    session: Session,
    review: Review,
    *,
    staged: bool,
    rationale: str | None,
    username: str,
    row_version: int | None = None,
) -> Review:
    """Stage a review in, or descope it out.

    Rule 6: descoping always requires a rationale, and the API refuses the state rather
    than recording it and flagging it afterwards (decision D1).
    """
    item = _item(review)
    _check_version(item, row_version)

    if staged:
        item.staged = True
        item.descope_rationale = None
        audit.record(
            session, username=username, review=review,
            action="Staged IN", detail="Selected for the plan",
        )
    else:
        text = staging.validate_descope(rationale)
        item.staged = False
        item.descope_rationale = text
        item.planned_quarter = None
        audit.record(session, username=username, review=review, action="Descoped", detail=text)
        session.add(ReviewNote(
            review_id=review.id, author=username, text=f"[Descoped] {text}", created_at=utcnow()
        ))

    _touch(item)
    return review


def set_priority_override(
    session: Session,
    review: Review,
    *,
    value: float,
    rationale: str | None,
    username: str,
    weights,
    row_version: int | None = None,
) -> Review:
    """Rule 3: store the override beside the computed value, never over it."""
    item = _item(review)
    _check_version(item, row_version)
    clamped, text = scoring.validate_override(value, rationale)

    view = mapping.to_view(review)
    computed = (
        scoring.computed_priority(view.scores, weights) if view.scores is not None else None
    )

    item.priority_override = clamped
    item.priority_override_rationale = text
    _touch(item)

    detail = (
        f"computed {computed:.2f} -> set {clamped:.2f}. Rationale: {text}"
        if computed is not None
        else f"set {clamped:.2f}. Rationale: {text}"
    )
    audit.record(session, username=username, review=review,
                 action="Priority override", detail=detail)
    session.add(ReviewNote(
        review_id=review.id, author=username,
        text=f"[Priority override -> {clamped:.2f}] {text}", created_at=utcnow(),
    ))
    return review


def clear_priority_override(
    session: Session, review: Review, *, username: str, weights, row_version: int | None = None
) -> Review:
    item = _item(review)
    _check_version(item, row_version)
    item.priority_override = None
    item.priority_override_rationale = None
    _touch(item)

    view = mapping.to_view(review)
    computed = scoring.computed_priority(view.scores, weights) if view.scores else None
    audit.record(
        session, username=username, review=review, action="Priority override",
        detail=f"reset to computed {computed:.2f}" if computed is not None else "reset to computed",
    )
    return review


def set_quarter(
    session: Session,
    review: Review,
    *,
    quarter: Quarter | None,
    username: str,
    row_version: int | None = None,
) -> Review:
    item = _item(review)
    _check_version(item, row_version)
    previous = item.planned_quarter or "—"
    item.planned_quarter = quarter.value if quarter else None
    _touch(item)
    audit.record(
        session, username=username, review=review, action="Planned quarter",
        detail=f"{previous} -> {quarter.value if quarter else '—'}",
    )
    return review


def set_effort(
    session: Session, review: Review, *, size: EffortSize, username: str
) -> Review:
    previous = review.effort_size
    if previous == size:
        return review
    review.effort_size = size
    audit.record(session, username=username, review=review, action="Effort edited",
                 detail=f"{previous} -> {size.value}")
    return review


def set_fte(session: Session, review: Review, *, fte: int | None, username: str) -> Review:
    previous = mapping.to_view(review).fte
    review.fte_override = fte
    now = mapping.to_view(review).fte
    if previous != now:
        audit.record(session, username=username, review=review, action="FTE edited",
                     detail=f"{previous} -> {now} FTE")
    return review


def set_locations(
    session: Session, review: Review, *, locations: Sequence[str], reference: Sequence[str],
    username: str,
) -> Review:
    """Rule 13: replace the multi-location set, ordered by the reference list."""
    previous = [loc.location for loc in sorted(review.locations, key=lambda x: x.sort_order)]
    unique = list(dict.fromkeys(l.strip() for l in locations if l and l.strip()))
    ordered = [l for l in reference if l in unique] + [l for l in unique if l not in reference]

    review.locations.clear()
    session.flush()
    for i, name in enumerate(ordered):
        review.locations.append(ReviewLocation(review_id=review.id, location=name, sort_order=i))

    if previous != ordered:
        audit.record(
            session, username=username, review=review, action="Locations updated",
            detail=f"{'; '.join(previous) or '(none)'} -> {'; '.join(ordered) or '(none)'}",
        )
    return review


def record_steward(
    session: Session, review: Review, *, steward_name: str, username: str
) -> Review:
    """Rule 14: applies to Risk Radar inputs -- name, who recorded it, and when."""
    name = (steward_name or "").strip()
    if not name:
        from app.domain.errors import RationaleRequired

        raise RationaleRequired("The risk steward's name is required.")

    if review.steward is None:
        review.steward = StewardConsultation(
            review_id=review.id, steward_name=name, recorded_by=username, recorded_at=utcnow()
        )
    else:
        review.steward.steward_name = name
        review.steward.recorded_by = username
        review.steward.recorded_at = utcnow()

    audit.record(session, username=username, review=review,
                 action="Risk steward consulted", detail=f"{name} (recorded by {username})")
    return review


def add_note(session: Session, review: Review, *, text: str, username: str) -> ReviewNote:
    note = ReviewNote(review_id=review.id, author=username, text=text.strip(),
                      created_at=utcnow())
    session.add(note)
    audit.record(session, username=username, review=review, action="Note", detail=text.strip())
    return note


def validate_new_review(origin: Origin, mandated: bool, rationale: str | None) -> str:
    """Rule 4 plus both add-forms: origin must agree, and a rationale is required."""
    staging.validate_origin(origin, mandated)
    text = (rationale or "").strip()
    if not text:
        from app.domain.errors import RationaleRequired

        raise RationaleRequired("A rationale is required to add a review.")
    return text

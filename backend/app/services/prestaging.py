"""Helios pre-staging."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domain import helios
from app.models import HeliosPrestaging, Review
from app.services import audit, mapping


def ensure(session: Session, review: Review) -> HeliosPrestaging:
    if review.prestaging is None:
        view = mapping.to_view(review)
        review.prestaging = HeliosPrestaging(
            review_id=review.id,
            target_start=review.go_live if review.mandated else None,
            values={
                "reviewId": f"AREV-{review.ref.replace('.', '')}",
                "title": review.title,
                "reviewType": "Core - Externally mandated" if review.mandated else "Additional",
                "assuranceFunction": view.assurance_function,
                "reviewTeam": view.sub_team or "",
                "business": review.business or "",
                "riskFlags": "NA",
                "esgFlag": "No",
                "status": "Planned",
            },
        )
        session.add(review.prestaging)
    return review.prestaging


def read(session: Session, review: Review) -> dict:
    record = ensure(session, review)
    values = dict(record.values or {})
    values["location"] = "; ".join(mapping.to_view(review).locations)
    values.update(helios.derived_values(record.target_start))
    return {
        "ref": review.ref,
        "title": review.title,
        "mandated": review.mandated,
        "target_start": record.target_start.isoformat() if record.target_start else None,
        "values": values,
        "complete": helios.is_complete(values),
        "missing": helios.missing_fields(values),
    }


def update(
    session: Session, review: Review, *, changes: dict, username: str
) -> HeliosPrestaging:
    record = ensure(session, review)
    values = dict(record.values or {})

    for key, value in changes.items():
        if key in helios.DERIVED_FIELDS:
            continue  # derived from Target Start Date; never accepted from a client
        field = helios.FIELDS_BY_KEY.get(key)
        if field is None:
            continue
        if field.allowed and value and value not in field.allowed:
            from app.domain.errors import DomainError

            raise DomainError(f"{value!r} is not an allowed value for {field.label}.")

        if key == "targetStart":
            record.target_start = date.fromisoformat(value) if value else None
        values[key] = value
        audit.record(session, username=username, review=review, action="Pre-staging edit",
                     detail=f"{key} -> {value or '(cleared)'}")

    record.values = values
    return record


def export_rows(session: Session, reviews: list[Review]) -> list[list[str]]:
    rows = [helios.EXPORT_HEADER]
    for review in reviews:
        data = read(session, review)
        rows.append(helios.export_row(data["values"], _target_start(data)))
    return rows


def _target_start(data: dict) -> date | None:
    raw = data.get("target_start")
    return date.fromisoformat(raw) if raw else None

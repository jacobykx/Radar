"""The bridge from a planned review to its Helios row.

This is where the planning workflow meets the export half of the app: a `Review` carries
its Helios values, seeded from what planning already knows and enriched by hand on the
pre-staging screen. The column spec, the allowed values and the validation all come from
`helios.spec` / `helios.validation`, so there is one definition of what Helios accepts.
"""

from __future__ import annotations

from datetime import date

from .. import mapping, spec, validation
from .constants import Quarter
from .types import Review


def parse_go_live(raw: object) -> date | None:
    """Accepts what a planner types — ISO, `18 Mar 2027`, `Mar 2027` — or nothing."""
    return spec.parse_date(raw).value


def quarter_of(go_live: date | None) -> Quarter | None:
    if go_live is None:
        return None
    return Quarter(f"Q{(go_live.month - 1) // 3 + 1}")


def seed_values(review: Review) -> dict[str, str]:
    """The Helios row this review starts with, before anyone enriches it."""
    return mapping.to_helios({
        "ref": review.ref,
        "title": review.title,
        "team": review.assurance_function,
        "sub-team": review.sub_team,
        "business": review.business,
        "location": "; ".join(review.locations),
        "go-live": review.go_live.isoformat() if review.go_live else "",
        "mandated": review.mandated,
        "taxonomy": review.taxonomy_code,
    })


def values(review: Review) -> dict[str, str]:
    """Current values, back-filled from planning for anything not yet touched by hand."""
    seeded = seed_values(review)
    merged = {**seeded, **{k: v for k, v in review.helios.items() if str(v).strip()}}
    # Locations are owned by Risk Radar, not typed here, so planning always wins.
    merged["location"] = "; ".join(review.locations) or seeded.get("location", "")
    return merged


def read(review: Review) -> dict:
    """One pre-staging record: normalised values plus what is still missing."""
    clean, errors = validation.prepare_row(values(review))
    return {
        "ref": review.ref,
        "title": review.title,
        "mandated": review.mandated,
        "values": clean,
        "errors": [e.as_dict() for e in errors],
        "complete": not errors,
    }


def apply(review: Review, changes: dict) -> dict[str, str]:
    """Store the edits that name a real, editable column. Returns what was applied."""
    applied: dict[str, str] = {}
    current = values(review)
    for key, value in (changes or {}).items():
        field = spec.BY_KEY.get(key)
        if field is None or field.type == "derived":
            continue  # derived columns follow the Target Start Date, never a caller
        text = "" if value is None else str(value)
        if text == current.get(key, ""):
            continue
        review.helios[key] = text
        applied[key] = text
    return applied


def rows(reviews: list[Review]) -> list[dict[str, str]]:
    """The in-plan population, as Helios rows, ready for validation and export."""
    return [values(r) for r in reviews]

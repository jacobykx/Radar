"""Map approved reviews onto Helios columns.

The input is whatever the planning side calls an approved review — a ref, a title, a team,
a go-live date. This module turns one into a Helios row; `validation` then decides whether
that row is good enough to ship. Nothing here validates, and nothing here rejects: a field
it cannot fill is left empty so the required-field check reports it in the normal way.
"""

from __future__ import annotations

import csv
import io

from . import reference, spec

#: Planning-side field names accepted for each Helios column, on top of the column's own
#: key and label. Matched on `reference.key`, so case and spacing do not matter.
_ALIASES: dict[str, tuple[str, ...]] = {
    "reviewId": ("ref", "reference", "review id", "lookup key", "id"),
    "title": ("review", "review title", "candidate review", "name"),
    "reviewDetail": ("rationale", "review rationale", "detail", "review detail"),
    "reviewType": ("type",),
    "reviewCategory": ("category",),
    "assuranceFunction": ("team", "assurance team", "function"),
    "reviewLead": ("lead", "owner", "staff id", "review lead"),
    "reviewTeam": ("subteam", "sub-team", "sub team"),
    "business": ("business area", "bu"),
    "location": ("locations", "location(s)", "country", "countries"),
    "riskTaxonomy": ("taxonomy", "risk taxonomy l3", "domain"),
    "scopeRationale": ("scope", "scope and rationale", "review scope"),
    "targetStart": ("go live", "golive", "go-live", "start date", "target start"),
    "legalEntity": ("entity",),
}

#: Extra planning-side inputs that steer the mapping without being columns themselves.
_MANDATED_KEYS = ("mandated", "core", "externally mandated")
_TRUE = {"true", "yes", "y", "1", "mandated"}


def to_helios(review: dict[str, object]) -> dict[str, str]:
    """Build a Helios row from an approved review.

    Defaults follow the MVP: a mandated review is Core - Externally mandated, anything else
    is Additional. Unlike the MVP, a go-live date becomes the target start whoever supplied
    it — a non-mandated review with a known date should not have to have it retyped.
    """
    source = {reference.key(k): v for k, v in review.items()}
    mandated = _flag(source)

    row: dict[str, str] = {}
    for f in spec.FIELDS:
        if f.type == "derived":
            continue
        value = _lookup(source, f)
        row[f.key] = "" if value is None else str(value).strip()

    ref = row.get("reviewId", "")
    row["reviewId"] = ref if ref.upper().startswith("AREV-") else _lookup_key(ref)

    # Seed defaults for a review the planning side is handing over for the first time. A
    # source that named the column and left it blank meant it, so these never overwrite.
    defaults = {
        "reviewType": "Core - Externally mandated" if mandated else "Additional",
        "status": "Planned",
        "riskFlags": "NA",
        "esgFlag": "No",
    }
    for key, default in defaults.items():
        if not row[key] and not _named(source, spec.BY_KEY[key]):
            row[key] = default

    # The planning side records one rationale; Helios wants it in both narrative columns. Only
    # mirror into a column the source never named — if it named one and left it empty, that is
    # a decision, and copying over it would stop a Helios file round-tripping through here.
    rationale = row["reviewDetail"] or row["scopeRationale"]
    for key in ("reviewDetail", "scopeRationale"):
        if not row[key] and not _named(source, spec.BY_KEY[key]):
            row[key] = rationale

    return row


def to_helios_many(reviews: list[dict[str, object]]) -> list[dict[str, str]]:
    return [to_helios(r) for r in reviews]


def from_csv(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Read approved reviews from a CSV export, returning (rows, unrecognised headers).

    Headers are matched against Helios keys, Helios labels and the planning-side aliases,
    so both a re-imported Helios file and a raw planning extract load without a mapping step.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = [h for h in (reader.fieldnames or []) if h and h.strip()]
    if not headers:
        return [], []

    resolved = {h: _resolve(h) for h in headers}
    unknown = sorted(
        h.strip() for h, key in resolved.items() if key is None and not _known_non_column(h)
    )

    rows: list[dict[str, str]] = []
    for record in reader:
        review: dict[str, object] = {}
        for header, key in resolved.items():
            if key is not None:
                review[key] = record.get(header) or ""
            elif _is_flag(header):  # not a column, but it steers the mapping
                review["mandated"] = record.get(header) or ""
        if any(str(v).strip() for v in review.values()):
            rows.append(to_helios(review))

    return rows, unknown


def blank_row() -> dict[str, str]:
    """An empty row carrying only the defaults every Helios row starts with."""
    return to_helios({})


def _lookup(source: dict[str, object], f: spec.Field) -> object | None:
    for name in (f.key, f.label, *_ALIASES.get(f.key, ())):
        value = source.get(reference.key(name))
        if value not in (None, ""):
            return value
    return None


def _named(source: dict[str, object], f: spec.Field) -> bool:
    """True when the source carried this column under its own Helios name, empty or not."""
    return any(reference.key(name) in source for name in (f.key, f.label))


def _resolve(header: str) -> str | None:
    wanted = reference.key(header)
    for f in spec.FIELDS:
        if f.type == "derived":
            continue  # a re-imported Helios file carries these; they are recomputed
        names = (f.key, f.label, *_ALIASES.get(f.key, ()))
        if wanted in {reference.key(n) for n in names}:
            return f.key
    return None


def _is_flag(header: str) -> bool:
    return reference.key(header) in {reference.key(k) for k in _MANDATED_KEYS}


def _known_non_column(header: str) -> bool:
    """Headers we understand but do not read: the mandated flag, and the derived columns.

    A re-imported Helios file carries Plan/IAP quarter and year. Dropping them is correct —
    they are recomputed from the Target Start Date — but they are not *unrecognised*, and
    reporting them as such would send someone looking for a mapping bug that isn't there.
    """
    if _is_flag(header):
        return True
    wanted = reference.key(header)
    return any(
        wanted in {reference.key(spec.BY_KEY[k].key), reference.key(spec.BY_KEY[k].label)}
        for k in spec.DERIVED
    )


def _lookup_key(ref: str) -> str:
    """`3.1` -> `AREV-31`, matching the prototype's lookup key convention."""
    stripped = ref.replace(".", "").replace(" ", "").strip()
    return f"AREV-{stripped}" if stripped else ""


def _flag(source: dict[str, object]) -> bool:
    for name in _MANDATED_KEYS:
        value = source.get(reference.key(name))
        if value is not None:
            return str(value).strip().casefold() in _TRUE
    return False

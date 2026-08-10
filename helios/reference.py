"""Reference data and its normalisation.

Two jobs:

1. Hold the lists Helios keys against (business, location). In production these come from
   the KBD reference-data mapper; `LISTS` is the seam where that feed lands.
2. Normalise an incoming value onto the canonical spelling. Planning-side data arrives with
   hyphens where the reference list has em dashes, stray casing and doubled spaces — all of
   which Helios rejects. Matching is done on a squashed key so those differences resolve
   silently, and anything that still does not match is reported rather than guessed at.
"""

from __future__ import annotations

BUSINESSES: tuple[str, ...] = (
    "CIB — Global Banking",
    "CIB — Markets & Securities Services",
    "CIB — Global Payments Solutions",
    "IWPB — Wealth",
    "IWPB — Personal Banking",
    "Global Functions — Finance",
    "Global Functions — Risk & Compliance",
    "Global Functions — Technology",
    "Corporate Centre",
)

LOCATIONS: tuple[str, ...] = (
    "Global", "UK", "Hong Kong", "Mainland China", "Singapore", "Malaysia", "India", "UAE",
    "France", "Germany", "USA", "Canada", "Mexico", "Brazil", "Australia",
)

#: Named lists, referenced by `spec.Field.reference`.
LISTS: dict[str, tuple[str, ...]] = {
    "business": BUSINESSES,
    "location": LOCATIONS,
}

#: Dash-like characters that all mean "-" for matching purposes.
_DASHES = str.maketrans({"—": "-", "–": "-", "‒": "-", "−": "-"})

#: Values written differently on the planning side than in the reference lists.
_ALIASES: dict[str, str] = {
    "uk": "UK",
    "united kingdom": "UK",
    "gb": "UK",
    "us": "USA",
    "united states": "USA",
    "hk": "Hong Kong",
    "china": "Mainland China",
    "prc": "Mainland China",
    "uae": "UAE",
    "group": "Global",
}


def key(value: object) -> str:
    """Comparison key: case-, dash- and whitespace-insensitive."""
    text = str(value or "").translate(_DASHES).casefold()
    return " ".join(text.replace("&", "and").split())


def canonical(value: object, choices: tuple[str, ...]) -> str | None:
    """The canonical spelling of `value` within `choices`, or None if it is not in the list."""
    wanted = key(value)
    if not wanted:
        return None

    lookup = {key(choice): choice for choice in choices}
    if wanted in lookup:
        return lookup[wanted]

    aliased = _ALIASES.get(wanted)
    return lookup.get(key(aliased)) if aliased else None


def normalise(value: object, choices: tuple[str, ...]) -> tuple[str, bool]:
    """Return (canonical value, ok). An empty input is ok — required-ness is checked later.

    An unrecognised value is returned unchanged rather than dropped. It never reaches the
    CSV — the export is gated on there being no errors — but it stays on screen, which is
    the only way the person fixing it can see what they need to fix.
    """
    text = str(value or "").strip()
    if not text:
        return "", True

    match = canonical(text, choices)
    return (match, True) if match else (text, False)


def normalise_many(value: object, choices: tuple[str, ...]) -> tuple[str, list[str]]:
    """Normalise a multi-value field, returning the joined value and any unknown entries.

    Accepts semicolon- or comma-separated input and always emits `"; "`-separated output,
    de-duplicated with the first occurrence winning and input order preserved. Unknown
    entries are kept in place, for the same reason as `normalise`.
    """
    raw = str(value or "").replace(",", ";")
    seen: dict[str, str] = {}
    unknown: list[str] = []

    for part in (p.strip() for p in raw.split(";")):
        if not part:
            continue
        match = canonical(part, choices)
        if match is None and part not in unknown:
            unknown.append(part)
        resolved = match if match is not None else part
        seen.setdefault(key(resolved), resolved)

    return "; ".join(seen.values()), unknown


def choices_for(name: str) -> tuple[str, ...]:
    return LISTS.get(name, ())

"""The Helios bulk-upload column spec.

Single source of truth for this app: the column order below *is* the CSV column order,
and every other module reads the field set from here rather than restating it.

The field set comes from the shared Planning Key Fields spec. Plan/IAP quarter and year
are derived from the Target Start Date and are never accepted from the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Free-text go-live dates are common in the planning-side data ("18 Mar 2027", "Sep 2026").
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

REVIEW_TYPES: tuple[str, ...] = (
    "Core - Externally mandated",
    "Core - Internally mandated",
    "Additional",
    "Opinion Paper",
)

REVIEW_CATEGORIES: tuple[str, ...] = (
    "Global", "Regional", "Country", "Single - Market Review", "Multi - Market Review",
)

ASSURANCE_FUNCTIONS: tuple[str, ...] = (
    "Financial Crime Assurance",
    "Regulatory Compliance Assurance",
    "United States Assurance",
    "China Assurance",
    "Traded Risk Assurance",
    "Treasury Risk Assurance",
    "Regulatory Reporting Assurance",
    "Group Insurance Assurance",
    "Wholesale Credit Risk Unit Assurance",
    "Continental Europe Assurance",
    "Singapore Assurance",
    "Malaysia Assurance",
    "Innovation Bank Assurance",
)

REVIEW_TEAMS: tuple[str, ...] = (
    "Hong Kong (FC)", "UK (FC)", "CIB (FC)", "Fraud", "AML", "Sanctions", "IWPB (FC)",
    "IWPB (RC)", "MSS (RC)", "CIB (RC)", "CIB Asia & MENAT (RC)", "Hong Kong (RC)", "UK (RC)",
    "China", "Continental Europe", "Singapore", "Innovation Bank Assurance", "Global", "LATAM",
    "USA", "ASP", "Canada", "Europe", "DBS & GF", "MENAT", "UKRFB",
)


@dataclass(frozen=True)
class Field:
    """One Helios column.

    `allowed` is a closed list held here; `reference` names a list held in `reference.py`
    because it is owned by the KBD reference-data mapper and changes without a release.
    """

    key: str
    label: str
    type: str = "text"  # text | textarea | select | date | multi | derived
    group: str = "existing"  # existing | change | system — drives the UI legend
    allowed: tuple[str, ...] = ()
    reference: str = ""
    hint: str = ""
    full_width: bool = False

    @property
    def required(self) -> bool:
        return self.key in REQUIRED


FIELDS: tuple[Field, ...] = (
    Field("reviewId", "Lookup Key (Review ID)"),
    Field("title", "Title", full_width=True),
    Field("reviewDetail", "Review Detail (Review Rationale)", "textarea", "change",
          full_width=True),
    Field("reviewType", "Review Type", "select", allowed=REVIEW_TYPES),
    Field("reviewCategory", "Review Category", "select", allowed=REVIEW_CATEGORIES),
    Field("assuranceFunction", "Assurance Function", "select", "change",
          allowed=ASSURANCE_FUNCTIONS),
    Field("reviewLead", "Review Lead (Staff ID)"),
    Field("reviewTeam", "Review Team", "select", allowed=REVIEW_TEAMS),
    Field("business", "Business", "select", reference="business",
          hint="KBD Reference Data Mapper"),
    Field("location", "Location(s)", "multi", reference="location",
          hint="KBD Reference Data Mapper — semicolon separated"),
    Field("legalEntity", "Legal Entity", hint="KBD Reference Data Mapper"),
    Field("riskTaxonomy", "Risk Taxonomy", hint="Group Risk Taxonomy"),
    Field("riskFlags", "Risk Flags", "select", allowed=("FRB/DPA", "Swap Dealer", "Volcker", "NA")),
    Field("esgFlag", "ESG Flag", "select", allowed=("Yes", "No")),
    Field("conductOutcome", "Conduct Outcome", hint="See Assurance Reference Data"),
    Field("scopeRationale", "Review Scope and Rationale", "textarea", full_width=True),
    Field("gscCoverage", "GSC Coverage"),
    Field("status", "Assurance Review Status", "select", "change", allowed=("Planned",)),
    Field("targetStart", "Target Start Date", "date"),
    Field("planQuarter", "Plan Quarter", "derived", "system"),
    Field("iapQuarter", "IAP Quarter", "derived", "system"),
    Field("planYear", "Plan Year", "derived", "system"),
    Field("iapYear", "IAP Year", "derived", "system"),
    Field("materialControls", "Material Controls"),
    Field("auditability", "Auditability"),
    Field("cancellationCategory", "Cancellation Category", "change"),
    Field("reasonCancellation", "Reason for Cancellation", "textarea", full_width=True),
)

BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}

#: Without these a row is not a valid Helios upload row.
#:
#: The first seven are the Planning Key Fields spec's required set. `reviewId` and `title`
#: are added here: Helios keys the upload on the lookup key, so a row without one (or
#: without a title) cannot land, even though the spec leaves them implicit because the
#: planning tool always populates them.
REQUIRED: tuple[str, ...] = (
    "reviewId", "title", "reviewType", "reviewCategory", "assuranceFunction",
    "reviewLead", "reviewTeam", "targetStart", "scopeRationale",
)

#: Never accepted from a caller — recomputed from Target Start Date on every read.
DERIVED: tuple[str, ...] = ("planQuarter", "iapQuarter", "planYear", "iapYear")

HEADER: list[str] = [f.label for f in FIELDS]


@dataclass
class ParsedDate:
    """Outcome of parsing a user- or feed-supplied date."""

    value: date | None = None
    raw: str = ""
    ok: bool = True
    accepted: list[str] = field(default_factory=list)

    @property
    def iso(self) -> str:
        return self.value.isoformat() if self.value else ""


_FORMATS = "YYYY-MM-DD, DD/MM/YYYY, '18 Mar 2027' or 'Mar 2027'"


def parse_date(raw: object) -> ParsedDate:
    """Parse the date formats the planning side actually produces.

    Anything unparseable comes back `ok=False` rather than raising, so the caller can
    report it as a row error alongside the others instead of aborting the batch.
    """
    text = str(raw or "").strip()
    if not text:
        return ParsedDate(raw=text)

    try:  # ISO first — what the UI and any sane feed sends.
        return ParsedDate(value=date.fromisoformat(text), raw=text)
    except ValueError:
        pass

    parts = text.replace(",", " ").replace("/", " ").replace("-", " ").split()

    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
        day, month, year = (int(p) for p in parts)  # DD/MM/YYYY
    elif len(parts) == 3 and parts[0].isdigit():
        day, month, year = int(parts[0]), _MONTHS.get(parts[1][:3].lower(), 0), _int(parts[2])
    elif len(parts) == 2:  # "Mar 2027" — first of the month, as the prototype does
        day, month, year = 1, _MONTHS.get(parts[0][:3].lower(), 0), _int(parts[1])
    else:
        return ParsedDate(raw=text, ok=False)

    try:
        return ParsedDate(value=date(year, month, day), raw=text)
    except ValueError:
        return ParsedDate(raw=text, ok=False)


def _int(text: str) -> int:
    return int(text) if text.isdigit() else 0


def derive(target_start: date | None) -> dict[str, str]:
    """Plan/IAP quarter and year follow the Target Start Date. Nothing else sets them."""
    if target_start is None:
        return dict.fromkeys(DERIVED, "")
    quarter = f"Q{(target_start.month - 1) // 3 + 1}"
    year = str(target_start.year)
    return {
        "planQuarter": quarter,
        "iapQuarter": quarter,
        "planYear": year,
        "iapYear": year,
    }


def date_formats() -> str:
    return _FORMATS

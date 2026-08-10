"""Helios pre-staging.

The field set comes from the shared Planning Key Fields spec; only fields present there
are captured and exported. Plan/IAP quarter and year are derived from the Target Start
Date and are never user-entered. A review is Helios-ready once every required field
carries a value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from app.domain.constants import Quarter

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


class FieldGroup(str, Enum):
    """Where the field comes from -- drives the legend on the pre-staging screen."""

    EXISTING = "existing"
    CHANGE = "change"
    SYSTEM = "system"


@dataclass(frozen=True)
class HeliosField:
    key: str
    label: str
    type: str
    group: FieldGroup = FieldGroup.EXISTING
    allowed: tuple[str, ...] | None = None
    hint: str | None = None
    full_width: bool = False


#: Reference-data-backed lists are resolved at request time, not frozen here.
REFERENCE_BACKED: dict[str, str] = {"business": "business", "location": "location"}

HELIOS_FIELDS: tuple[HeliosField, ...] = (
    HeliosField("reviewId", "Lookup Key (Review ID)", "text"),
    HeliosField("title", "Title", "text", full_width=True),
    HeliosField(
        "reviewDetail", "Review Detail (Review Rationale)", "textarea", FieldGroup.CHANGE,
        full_width=True,
    ),
    HeliosField("reviewType", "Review Type", "select", allowed=(
        "Core - Externally mandated", "Core - Internally mandated", "Additional", "Opinion Paper")),
    HeliosField("reviewCategory", "Review Category", "select", allowed=(
        "Global", "Regional", "Country", "Single - Market Review", "Multi - Market Review")),
    HeliosField(
        "assuranceFunction", "Assurance Function", "select", FieldGroup.CHANGE,
        allowed=ASSURANCE_FUNCTIONS,
    ),
    HeliosField("reviewLead", "Review Lead (Staff ID)", "text"),
    HeliosField("reviewTeam", "Review Team", "select", allowed=REVIEW_TEAMS),
    HeliosField("business", "Business", "select", hint="KBD Reference Data Mapper"),
    HeliosField(
        "location", "Location(s)", "multiloc", hint="KBD Reference Data Mapper - multi-select",
    ),
    HeliosField("legalEntity", "Legal Entity", "text", hint="KBD Reference Data Mapper"),
    HeliosField("riskTaxonomy", "Risk Taxonomy", "text", hint="Group Risk Taxonomy"),
    HeliosField(
        "riskFlags", "Risk Flags", "select", allowed=("FRB/DPA", "Swap Dealer", "Volcker", "NA"),
    ),
    HeliosField("esgFlag", "ESG Flag", "select", allowed=("Yes", "No")),
    HeliosField("conductOutcome", "Conduct Outcome", "text", hint="See Assurance Reference Data"),
    HeliosField("scopeRationale", "Review Scope and Rationale", "textarea", full_width=True),
    HeliosField("gscCoverage", "GSC Coverage", "text"),
    HeliosField(
        "status", "Assurance Review Status", "select", FieldGroup.CHANGE, allowed=("Planned",),
    ),
    HeliosField("targetStart", "Target Start Date", "date"),
    HeliosField("planQuarter", "Plan Quarter", "derived", FieldGroup.SYSTEM),
    HeliosField("iapQuarter", "IAP Quarter", "derived", FieldGroup.SYSTEM),
    HeliosField("planYear", "Plan Year", "derived", FieldGroup.SYSTEM),
    HeliosField("iapYear", "IAP Year", "derived", FieldGroup.SYSTEM),
    HeliosField("materialControls", "Material Controls", "text"),
    HeliosField("auditability", "Auditability", "text"),
    HeliosField("cancellationCategory", "Cancellation Category", "text", FieldGroup.CHANGE),
    HeliosField("reasonCancellation", "Reason for Cancellation", "textarea", full_width=True),
)

FIELDS_BY_KEY: dict[str, HeliosField] = {f.key: f for f in HELIOS_FIELDS}

#: Without these, the review is not Helios-ready.
REQUIRED_FIELDS: tuple[str, ...] = (
    "reviewType", "reviewCategory", "assuranceFunction", "reviewLead", "reviewTeam",
    "targetStart", "scopeRationale",
)

DERIVED_FIELDS: tuple[str, ...] = ("planQuarter", "iapQuarter", "planYear", "iapYear")


@dataclass
class Derived:
    quarter: Quarter | None = None
    year: str = ""


def derive_from_start(target_start: date | None) -> Derived:
    """Plan/IAP quarter and year follow the Target Start Date. Nothing else sets them."""
    if target_start is None:
        return Derived()
    return Derived(
        quarter=Quarter(f"Q{(target_start.month - 1) // 3 + 1}"),
        year=str(target_start.year),
    )


def derived_values(target_start: date | None) -> dict[str, str]:
    d = derive_from_start(target_start)
    quarter = d.quarter.value if d.quarter else ""
    return {"planQuarter": quarter, "iapQuarter": quarter, "planYear": d.year, "iapYear": d.year}


def missing_fields(values: dict[str, object]) -> list[str]:
    return [k for k in REQUIRED_FIELDS if not str(values.get(k) or "").strip()]


def is_complete(values: dict[str, object]) -> bool:
    return not missing_fields(values)


def export_row(values: dict[str, object], target_start: date | None) -> list[str]:
    """One export line, in spec order, with the derived fields resolved."""
    derived = derived_values(target_start)
    row = []
    for f in HELIOS_FIELDS:
        if f.type == "derived":
            row.append(derived.get(f.key, ""))
        else:
            row.append(str(values.get(f.key) or ""))
    return row


EXPORT_HEADER: list[str] = [f.label for f in HELIOS_FIELDS]

"""Assurance-methodology constants.

These are methodology facts, not configuration: changing a value here changes how the
plan is shaped. Each is traced to the prototype it came from, and mirrors
`backend/app/domain/constants.py` — see `helios/planning/__init__.py` for why there are
two copies.
"""

from __future__ import annotations

from enum import Enum


class Quarter(str, Enum):
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


QUARTERS: tuple[Quarter, ...] = (Quarter.Q1, Quarter.Q2, Quarter.Q3, Quarter.Q4)


class EffortSize(str, Enum):
    S = "S"
    M = "M"
    L = "L"


#: Assurance days by effort size (prototype SIZE_DAYS).
SIZE_DAYS: dict[EffortSize, int] = {EffortSize.S: 60, EffortSize.M: 90, EffortSize.L: 120}

#: FTE to run a review of each size, before any per-review override (prototype SIZE_FTE).
SIZE_FTE: dict[EffortSize, int] = {EffortSize.S: 2, EffortSize.M: 3, EffortSize.L: 4}


class Origin(str, Enum):
    """Where a review came from. Mandated reviews are always REGULATORY."""

    REGULATORY = "Regulatory Assurance"
    RISK = "Risk Assurance"
    RADAR = "Risk Radar inputs"


class ApprovalRoute(str, Enum):
    IRR = "IRR"
    RCA = "RCA"
    STANDARD = "Standard"


#: The single sign-off gate on each route (prototype gatesOf).
ROUTE_GATE: dict[ApprovalRoute, str] = {
    ApprovalRoute.IRR: "IRR sign-off",
    ApprovalRoute.RCA: "RCA owner sign-off",
    ApprovalRoute.STANDARD: "1LOD / L2 sign-off",
}


class ApprovalStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    RETURNED = "Returned"


class Band(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    MANDATED = "Mandated"


#: Lower bound of each priority band on the 1-5 scale (prototype band()).
BAND_FLOOR: tuple[tuple[float, Band], ...] = (
    (4.3, Band.CRITICAL),
    (3.7, Band.HIGH),
    (3.0, Band.MEDIUM),
)

#: The four factors the scoring engine supplies. Read-only facts; the user's lever is the
#: weights, not these (prototype DRIVERS).
DRIVERS: tuple[tuple[str, str], ...] = (
    ("risk", "Risk score"),
    ("urgency", "Urgency index"),
    ("coverage_gap", "Coverage gap"),
    ("change", "Change index"),
)

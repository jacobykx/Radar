"""Synthetic fixtures, ported from the prototype.

This is mock data: illustrative reviews for a UK GSIB, with no real customer, employee or
supervisory content. The four driver scores stand in for a separate scoring engine — in
the tool they are read-only facts, and the planner's lever is the weights.
"""

from __future__ import annotations

from datetime import date

from .constants import EffortSize, Origin, Quarter
from .types import FunctionCapacity, Review, Scores

PLAN_YEAR = "2027"

TAXONOMY: tuple[tuple[str, str], ...] = (
    ("change-ai", "Change: data, models & AI"),
    ("op-res", "Operational resilience & third party"),
    ("prudential", "Prudential, credit & model risk"),
    ("fincrime", "Financial crime & AML"),
    ("conduct", "Conduct & Consumer Duty"),
)

#: Assurance function -> FTE available per quarter. Zero means the function is inactive:
#: it exists in the reference list but takes no demand in this plan.
FUNCTION_FTE: dict[str, int] = {
    "Financial Crime Assurance": 10,
    "Regulatory Compliance Assurance": 16,
    "Traded Risk Assurance": 8,
    "Treasury Risk Assurance": 8,
    "Wholesale Credit Risk Unit Assurance": 6,
    "Regulatory Reporting Assurance": 6,
    "United States Assurance": 0,
    "China Assurance": 0,
    "Group Insurance Assurance": 0,
    "Continental Europe Assurance": 0,
    "Singapore Assurance": 0,
    "Malaysia Assurance": 0,
    "Innovation Bank Assurance": 0,
}

SUB_TEAMS: dict[str, tuple[str, ...]] = {
    "Financial Crime Assurance": (
        "Hong Kong (FC)", "UK (FC)", "CIB (FC)", "Fraud", "AML", "Sanctions", "IWPB (FC)",
    ),
    "Regulatory Compliance Assurance": (
        "IWPB (RC)", "MSS (RC)", "CIB (RC)", "CIB Asia & MENAT (RC)", "Hong Kong (RC)", "UK (RC)",
    ),
}

#: Reviews sourced from RCA outcomes — mock, pending the real RCA/RRIS feed.
RCA_LINKED: frozenset[str] = frozenset({"3.1", "3.5", "4.3", "5.4", "6.1", "6.3", "7.1"})

# ref, taxonomy, title, function, sub-team, size, (risk, urgency, coverage gap, change),
# business, locations, and the regulatory detail where the review is mandated.
_ROWS: tuple[dict, ...] = (
    dict(ref="3.1", taxonomy="change-ai", title="SS1/23 model risk tested for AI/ML credibility",
         function="Traded Risk Assurance", size=EffortSize.M, scores=(4, 4, 3.5, 5),
         business="Global Functions — Risk & Compliance", locations=["Global"]),
    dict(ref="3.2", taxonomy="change-ai", title="Agentic AI in payments and markets",
         function="Traded Risk Assurance", size=EffortSize.M, scores=(4, 3, 5, 5),
         business="CIB — Markets & Securities Services", locations=["UK"]),
    dict(ref="3.3", taxonomy="change-ai",
         title="Third-party model/AI concentration & explainability",
         function="Regulatory Compliance Assurance", sub_team="CIB (RC)", size=EffortSize.S,
         scores=(4, 3, 3.5, 4), business="Global Functions — Technology", locations=["Global"]),
    dict(ref="3.4", taxonomy="change-ai", title="Frontier AI as a cyber threat amplifier",
         function="Regulatory Compliance Assurance", sub_team="CIB (RC)", size=EffortSize.M,
         scores=(5, 4, 5, 5), business="Global Functions — Technology", locations=["Global"]),
    dict(ref="3.5", taxonomy="change-ai", title="Data governance underneath the models",
         function="Regulatory Compliance Assurance", sub_team="MSS (RC)", size=EffortSize.S,
         scores=(4, 3, 3.5, 4), business="Global Functions — Risk & Compliance",
         locations=["UK"]),
    dict(ref="4.1", taxonomy="op-res",
         title="New incident & material-third-party reporting regime",
         function="Regulatory Reporting Assurance", size=EffortSize.L, scores=(4, 5, 5, 4),
         business="Global Functions — Technology", locations=["UK"], mandated=True,
         go_live=date(2027, 3, 18), regulator="PRA / FCA",
         regulation="PS7/26 · SS1/26 — operational incident & material third-party reporting",
         rris_ids=["RRIS-10421"]),
    dict(ref="4.2", taxonomy="op-res", title="Critical Third Parties: first designations",
         function="Regulatory Compliance Assurance", sub_team="CIB (RC)", size=EffortSize.S,
         scores=(3, 4, 3.5, 3), business="Global Functions — Technology", locations=["Global"]),
    dict(ref="4.3", taxonomy="op-res",
         title="SS1/21 post-transition: impact-tolerance credibility",
         function="Regulatory Compliance Assurance", sub_team="UK (RC)", size=EffortSize.M,
         scores=(4, 4, 3.5, 3), business="CIB — Global Payments Solutions", locations=["UK"]),
    dict(ref="4.4", taxonomy="op-res", title="Change risk across the BAU run-rate",
         function="Regulatory Compliance Assurance", sub_team="UK (RC)", size=EffortSize.S,
         scores=(4, 3, 5, 5), business="Global Functions — Technology", locations=["Global"]),
    dict(ref="5.1", taxonomy="prudential",
         title="Basel 3.1 implementation & off-cycle Pillar 2 review",
         function="Treasury Risk Assurance", size=EffortSize.L, scores=(4, 5, 4, 5),
         business="Global Functions — Finance", locations=["UK"], mandated=True,
         go_live=date(2027, 1, 1), regulator="PRA",
         regulation="PS1/26 — Basel 3.1 implementation", rris_ids=["RRIS-10388"]),
    dict(ref="5.2", taxonomy="prudential", title="NBFI and private-credit exposure",
         function="Wholesale Credit Risk Unit Assurance", size=EffortSize.M, scores=(5, 3, 3.5, 3),
         business="CIB — Global Banking", locations=["UK", "USA"]),
    dict(ref="5.3", taxonomy="prudential", title="AI-driven asset-price & private-credit risk",
         function="Wholesale Credit Risk Unit Assurance", size=EffortSize.S, scores=(5, 3, 5, 4),
         business="CIB — Markets & Securities Services", locations=["Global"]),
    dict(ref="5.4", taxonomy="prudential", title="Model risk on capital and IFRS 9 together",
         function="Treasury Risk Assurance", size=EffortSize.M, scores=(4, 4, 3, 3),
         business="Global Functions — Finance", locations=["UK"]),
    dict(ref="6.1", taxonomy="fincrime",
         title="Transaction-monitoring effectiveness & move to analytics",
         function="Financial Crime Assurance", sub_team="AML", size=EffortSize.M,
         scores=(4, 4, 3.5, 4), business="IWPB — Personal Banking", locations=["Hong Kong"]),
    dict(ref="6.2", taxonomy="fincrime", title="APP fraud and the PSR consolidation",
         function="Financial Crime Assurance", sub_team="Fraud", size=EffortSize.S,
         scores=(4, 4, 5, 3), business="CIB — Global Payments Solutions", locations=["UK"]),
    dict(ref="6.3", taxonomy="fincrime",
         title="Sanctions screening effectiveness & circumvention",
         function="Financial Crime Assurance", sub_team="Sanctions", size=EffortSize.S,
         scores=(4, 4, 3.5, 2), business="CIB — Global Banking",
         locations=["UAE", "UK", "Hong Kong"]),
    dict(ref="6.4", taxonomy="fincrime", title="AML supervisory reform (watch & adapt)",
         function="Financial Crime Assurance", sub_team="AML", size=EffortSize.S,
         scores=(3, 4, 3, 2), business="Global Functions — Risk & Compliance", locations=["UK"]),
    dict(ref="7.1", taxonomy="conduct", title="Consumer Duty: outcomes that evidence change",
         function="Regulatory Compliance Assurance", sub_team="IWPB (RC)", size=EffortSize.M,
         scores=(4, 4, 3.5, 2), business="IWPB — Wealth", locations=["Hong Kong"]),
    dict(ref="7.2", taxonomy="conduct", title="Non-financial misconduct becomes a Conduct Rule",
         function="Regulatory Compliance Assurance", sub_team="Hong Kong (RC)", size=EffortSize.S,
         scores=(4, 5, 5, 3), business="Global Functions — Risk & Compliance",
         locations=["Global"], mandated=True, go_live=date(2026, 9, 1), regulator="FCA",
         regulation="Non-financial misconduct — Conduct Rules expansion",
         rris_ids=["RRIS-10502"]),
    dict(ref="7.3", taxonomy="conduct", title="Fair value on closed books and legacy products",
         function="Regulatory Compliance Assurance", sub_team="IWPB (RC)", size=EffortSize.S,
         scores=(3, 3, 3.5, 2), business="IWPB — Wealth", locations=["UK"]),
)


def quarter_of(go_live: date | None) -> Quarter | None:
    """A mandated review starts in the quarter its obligation goes live."""
    if go_live is None:
        return None
    return Quarter(f"Q{(go_live.month - 1) // 3 + 1}")


def reviews() -> list[Review]:
    """A fresh candidate list. Mandated reviews start staged and quartered (rule 5)."""
    out: list[Review] = []
    for row in _ROWS:
        mandated = bool(row.get("mandated"))
        go_live = row.get("go_live")
        risk, urgency, coverage_gap, change = row["scores"]
        out.append(Review(
            ref=row["ref"],
            title=row["title"],
            assurance_function=row["function"],
            origin=Origin.REGULATORY if mandated else Origin.RADAR,
            mandated=mandated,
            effort_size=row["size"],
            scores=Scores(risk=risk, urgency=urgency, coverage_gap=coverage_gap, change=change),
            sub_team=row.get("sub_team", "") or "",
            taxonomy_code=row["taxonomy"],
            business=row.get("business", ""),
            locations=list(row.get("locations") or []),
            rca_linked=row["ref"] in RCA_LINKED,
            regulator=row.get("regulator", ""),
            regulation=row.get("regulation", ""),
            rris_ids=list(row.get("rris_ids") or []),
            go_live=go_live,
            staged=mandated,
            planned_quarter=quarter_of(go_live) if mandated else None,
        ))
    return out


def capacities() -> list[FunctionCapacity]:
    return [FunctionCapacity(name=name, fte_per_quarter=fte)
            for name, fte in FUNCTION_FTE.items()]


def reference() -> dict[str, list]:
    """The editable reference lists, as first shipped.

    Taxonomy entries are {code, label}: the code is the stable key stored against a
    review, the label is what a planner reads. Renaming a label leaves reviews intact.
    """
    from .. import reference as ref  # the canonical business/location lists

    return {
        "taxonomy": [{"code": code, "label": label} for code, label in TAXONOMY],
        "business": list(ref.BUSINESSES),
        "location": list(ref.LOCATIONS),
    }

"""The plan's data model.

One `Review` carries both the upstream facts (scores, size, obligation) and the planning
state (staged, quarter, override, sign-off). The prototype split these across `REVIEWS`
and `state[ref]`; keeping them together is what lets the domain rules be plain functions
over one object, and what lets the whole plan serialise to a single JSON document.

Everything here round-trips through `to_dict`/`from_dict` without losing a field, because
that is also the version-snapshot format.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from .constants import (
    SIZE_DAYS,
    SIZE_FTE,
    ApprovalStatus,
    EffortSize,
    Origin,
    Quarter,
)


def _enum(kind, value, default=None):
    """Tolerant enum lookup — an unknown stored value degrades rather than crashing."""
    try:
        return kind(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Weights:
    """The a/b/c/d priority weights. The user's only lever on priority."""

    risk: float = 1.0
    urgency: float = 1.0
    coverage_gap: float = 1.0
    change: float = 1.0

    @property
    def total(self) -> float:
        return self.risk + self.urgency + self.coverage_gap + self.change

    def to_dict(self) -> dict[str, float]:
        return {
            "risk": self.risk,
            "urgency": self.urgency,
            "coverage_gap": self.coverage_gap,
            "change": self.change,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> Weights:
        data = data or {}
        return cls(**{k: float(data.get(k, 1.0)) for k in
                      ("risk", "urgency", "coverage_gap", "change")})


@dataclass(frozen=True)
class Scores:
    """The four factor scores. Read-only facts from the upstream scoring engine."""

    risk: float
    urgency: float
    coverage_gap: float
    change: float

    def to_dict(self) -> dict[str, float]:
        return {
            "risk": self.risk,
            "urgency": self.urgency,
            "coverage_gap": self.coverage_gap,
            "change": self.change,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> Scores | None:
        if not data:
            return None
        return cls(**{k: float(data.get(k, 0)) for k in
                      ("risk", "urgency", "coverage_gap", "change")})


@dataclass
class Approval:
    """One gate's decision. There is exactly one gate per review (rule 10)."""

    status: ApprovalStatus = ApprovalStatus.PENDING
    by: str = ""
    at: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status.value, "by": self.by, "at": self.at, "note": self.note}

    @classmethod
    def from_dict(cls, data: dict | None) -> Approval:
        data = data or {}
        return cls(
            status=_enum(ApprovalStatus, data.get("status"), ApprovalStatus.PENDING),
            by=data.get("by", ""),
            at=data.get("at", ""),
            note=data.get("note", ""),
        )


@dataclass
class Comment:
    at: str
    user: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"at": self.at, "user": self.user, "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> Comment:
        return cls(at=data.get("at", ""), user=data.get("user", ""), text=data.get("text", ""))


@dataclass
class Review:
    """Everything the plan knows about one candidate review."""

    ref: str
    title: str
    assurance_function: str
    origin: Origin = Origin.RADAR
    mandated: bool = False
    effort_size: EffortSize = EffortSize.M
    scores: Scores | None = None
    #: What the scoring engine supplied, kept only once a score is edited by hand.
    seeded_scores: Scores | None = None
    sub_team: str = ""
    taxonomy_code: str = ""
    business: str = ""
    locations: list[str] = field(default_factory=list)
    fte_override: int | None = None
    rca_linked: bool = False
    regulator: str = ""
    regulation: str = ""
    rris_ids: list[str] = field(default_factory=list)
    go_live: date | None = None
    steward_consulted: bool = False
    steward_name: str = ""

    # ---- planning state
    staged: bool = False
    planned_quarter: Quarter | None = None
    priority_override: float | None = None
    priority_rationale: str = ""
    descope_rationale: str = ""
    approval: Approval = field(default_factory=Approval)
    comments: list[Comment] = field(default_factory=list)
    #: Helios pre-staging values, keyed by `helios.spec` field key.
    helios: dict[str, str] = field(default_factory=dict)

    # ---- derived

    @property
    def fte(self) -> int:
        """FTE required. The per-review override beats the size default (rule 7)."""
        if self.fte_override is not None:
            return self.fte_override
        return SIZE_FTE[self.effort_size]

    @property
    def effort_days(self) -> int:
        return SIZE_DAYS[self.effort_size]

    @property
    def descoped(self) -> bool:
        """Out of scope *with* a rationale. Merely un-staged is not descoped (rule 6)."""
        return not self.staged and bool(self.descope_rationale.strip())

    @property
    def rationale_outstanding(self) -> bool:
        """Out of the plan with nothing on record explaining why.

        Includes mandated reviews: the prototype lets one be taken out, so an obligation
        dropped without a reason is exactly the thing that must be chased, not prevented.
        """
        return not self.staged and not self.descoped

    @property
    def in_plan(self) -> bool:
        """Staged and not descoped: the population every later stage works on."""
        return self.staged and not self.descoped

    def with_quarter(self, quarter: Quarter | None) -> Review:
        return replace(self, planned_quarter=quarter)

    # ---- serialisation

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "title": self.title,
            "assurance_function": self.assurance_function,
            "origin": self.origin.value,
            "mandated": self.mandated,
            "effort_size": self.effort_size.value,
            "scores": self.scores.to_dict() if self.scores else None,
            "seeded_scores": self.seeded_scores.to_dict() if self.seeded_scores else None,
            "sub_team": self.sub_team,
            "taxonomy_code": self.taxonomy_code,
            "business": self.business,
            "locations": list(self.locations),
            "fte_override": self.fte_override,
            "rca_linked": self.rca_linked,
            "regulator": self.regulator,
            "regulation": self.regulation,
            "rris_ids": list(self.rris_ids),
            "go_live": self.go_live.isoformat() if self.go_live else None,
            "steward_consulted": self.steward_consulted,
            "steward_name": self.steward_name,
            "staged": self.staged,
            "planned_quarter": self.planned_quarter.value if self.planned_quarter else None,
            "priority_override": self.priority_override,
            "priority_rationale": self.priority_rationale,
            "descope_rationale": self.descope_rationale,
            "approval": self.approval.to_dict(),
            "comments": [c.to_dict() for c in self.comments],
            "helios": dict(self.helios),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Review:
        go_live = data.get("go_live")
        return cls(
            ref=data["ref"],
            title=data.get("title", ""),
            assurance_function=data.get("assurance_function", ""),
            origin=_enum(Origin, data.get("origin"), Origin.RADAR),
            mandated=bool(data.get("mandated")),
            effort_size=_enum(EffortSize, data.get("effort_size"), EffortSize.M),
            scores=Scores.from_dict(data.get("scores")),
            seeded_scores=Scores.from_dict(data.get("seeded_scores")),
            sub_team=data.get("sub_team") or "",
            taxonomy_code=data.get("taxonomy_code") or "",
            business=data.get("business") or "",
            locations=list(data.get("locations") or []),
            fte_override=data.get("fte_override"),
            rca_linked=bool(data.get("rca_linked")),
            regulator=data.get("regulator") or "",
            regulation=data.get("regulation") or "",
            rris_ids=list(data.get("rris_ids") or []),
            go_live=date.fromisoformat(go_live) if go_live else None,
            steward_consulted=bool(data.get("steward_consulted")),
            steward_name=data.get("steward_name") or "",
            staged=bool(data.get("staged")),
            planned_quarter=_enum(Quarter, data.get("planned_quarter")),
            priority_override=data.get("priority_override"),
            priority_rationale=data.get("priority_rationale") or "",
            descope_rationale=data.get("descope_rationale") or "",
            approval=Approval.from_dict(data.get("approval")),
            comments=[Comment.from_dict(c) for c in (data.get("comments") or [])],
            helios=dict(data.get("helios") or {}),
        )


@dataclass(frozen=True)
class FunctionCapacity:
    """FTE available per quarter for one assurance function.

    A function with no capacity is inactive: it takes no demand and is left out of the
    portfolio totals rather than showing as permanently over-committed.
    """

    name: str
    fte_per_quarter: int

    @property
    def is_active(self) -> bool:
        return self.fte_per_quarter > 0

    @property
    def annual_fte_quarters(self) -> int:
        return self.fte_per_quarter * len(Quarter)

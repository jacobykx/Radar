"""Plain domain views used by the services layer.

The rules in `app.domain` are pure functions over these structures, never over ORM
instances, so the methodology can be tested without a database. The repository layer
builds them from SQLAlchemy models.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from app.domain.constants import SIZE_FTE, EffortSize, Origin, Quarter


@dataclass(frozen=True)
class Weights:
    """The a/b/c/d priority weights. User-set; versioned per plan."""

    risk: float = 1.0
    urgency: float = 1.0
    coverage_gap: float = 1.0
    change: float = 1.0

    @property
    def total(self) -> float:
        return self.risk + self.urgency + self.coverage_gap + self.change


@dataclass(frozen=True)
class Scores:
    """The four factor scores. Read-only facts from the upstream scoring engine."""

    risk: float
    urgency: float
    coverage_gap: float
    change: float


@dataclass
class ReviewView:
    """Everything the domain rules need to know about one review."""

    ref: str
    title: str
    origin: Origin
    mandated: bool
    assurance_function: str
    effort_size: EffortSize
    scores: Scores | None = None
    sub_team: str | None = None
    taxonomy_code: str | None = None
    business: str | None = None
    locations: list[str] = field(default_factory=list)
    fte_override: int | None = None
    rca_linked: bool = False
    regulator: str | None = None
    regulation: str | None = None
    rris_ids: list[str] = field(default_factory=list)
    go_live: date | None = None

    # plan_item state
    staged: bool = False
    planned_quarter: Quarter | None = None
    priority_override: float | None = None
    descope_rationale: str | None = None

    @property
    def fte(self) -> int:
        """FTE required. The per-review override beats the size default."""
        if self.fte_override is not None:
            return self.fte_override
        return SIZE_FTE[self.effort_size]

    @property
    def descoped(self) -> bool:
        """Descoped means out of scope *with* a recorded rationale.

        A review that is merely un-staged is not descoped; the API refuses to put a
        review into that state (decision D1), so it only arises from seeded, imported
        or restored records and is reported as an outstanding rationale.
        """
        return not self.staged and bool((self.descope_rationale or "").strip())

    @property
    def rationale_outstanding(self) -> bool:
        return not self.staged and not self.mandated and not self.descoped

    @property
    def in_plan(self) -> bool:
        """Staged and not descoped: the population every downstream stage works on."""
        return self.staged and not self.descoped

    def with_quarter(self, quarter: Quarter | None) -> ReviewView:
        return replace(self, planned_quarter=quarter)


@dataclass(frozen=True)
class FunctionCapacity:
    """FTE available per quarter for one assurance function."""

    name: str
    fte_per_quarter: int
    is_active: bool = True

    @property
    def annual_fte_quarters(self) -> int:
        return self.fte_per_quarter * len(Quarter)

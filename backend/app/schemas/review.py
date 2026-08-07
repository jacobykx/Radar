"""Request and response models.

Rule 1 is enforced structurally: no write model has a field for risk, urgency,
coverage_gap or change, and `extra="forbid"` means sending one is a 422 rather than a
silently ignored key. A dropped field would hide the bug; a rejection surfaces it.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.constants import ApprovalStatus, Band, EffortSize, Origin, Quarter


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------------- responses


class ScoresOut(BaseModel):
    """Read-only facts from the scoring engine."""

    risk: float
    urgency: float
    coverage_gap: float
    change: float
    as_at: datetime
    source: str


class StewardOut(BaseModel):
    steward_name: str
    recorded_by: str
    recorded_at: datetime


class ApprovalOut(BaseModel):
    route: str
    gate: str
    status: ApprovalStatus
    approver: str | None = None
    decided_at: datetime | None = None
    comment: str | None = None


class NoteOut(BaseModel):
    author: str
    text: str
    created_at: datetime


class ReviewOut(BaseModel):
    ref: str
    title: str
    origin: Origin
    mandated: bool
    taxonomy_code: str | None
    taxonomy_label: str | None
    assurance_function: str
    sub_team: str | None
    business: str | None
    locations: list[str]
    effort_size: EffortSize
    effort_days: int
    fte: int
    fte_override: int | None
    regulator: str | None
    regulation: str | None
    rris_ids: list[str]
    rca_linked: bool
    go_live: date | None

    scores: ScoresOut | None
    computed_priority: float | None
    priority_override: float | None
    priority_override_rationale: str | None
    effective_priority: float | None
    band: Band

    staged: bool
    descoped: bool
    rationale_outstanding: bool
    descope_rationale: str | None
    planned_quarter: Quarter | None
    row_version: int

    route: str
    approval_status: ApprovalStatus
    steward: StewardOut | None
    notes: list[NoteOut] = Field(default_factory=list)


# ------------------------------------------------------------------------------ requests


class ReviewCreate(Strict):
    """Both add-forms. Factor scores are absent by design -- they are not the user's."""

    title: str = Field(min_length=1, max_length=500)
    origin: Origin
    assurance_function: str
    sub_team: str | None = None
    taxonomy_code: str | None = None
    business: str | None = None
    locations: list[str] = Field(default_factory=list)
    effort_size: EffortSize = EffortSize.M
    #: Enforced by the service, so every add-form path gives the same 400.
    rationale: str | None = None

    # Regulatory Assurance only
    regulator: str | None = None
    regulation: str | None = None
    rris_ids: str | None = None
    go_live: date | None = None


class ReviewPatch(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    effort_size: EffortSize | None = None
    fte_override: int | None = Field(default=None, ge=1, le=20)
    business: str | None = None
    taxonomy_code: str | None = None
    regulator: str | None = None
    regulation: str | None = None
    rris_ids: str | None = None


class LocationsPut(Strict):
    locations: list[str]


class PriorityOverridePost(Strict):
    value: float = Field(ge=0, le=5)
    #: Optional here, mandatory in the service. The rule belongs in one place, and the
    #: caller should get the domain's 400 with the rule named, not a schema 422.
    rationale: str | None = None
    row_version: int | None = None


class StagePost(Strict):
    staged: bool
    rationale: str | None = None
    row_version: int | None = None


class QuarterPatch(Strict):
    quarter: Quarter | None = None
    row_version: int | None = None


class StewardPost(Strict):
    steward_name: str = Field(min_length=1)


class NotePost(Strict):
    text: str = Field(min_length=1)


class ApprovalPost(Strict):
    decision: ApprovalStatus
    comment: str | None = None


class BulkApprovePost(Strict):
    team: str | None = None
    business: str | None = None
    location: str | None = None
    route: str | None = None
    status: ApprovalStatus | None = None


class WeightsIn(Strict):
    risk: float = Field(ge=0, le=3)
    urgency: float = Field(ge=0, le=3)
    coverage_gap: float = Field(ge=0, le=3)
    change: float = Field(ge=0, le=3)


class WeightsOut(BaseModel):
    risk: float
    urgency: float
    coverage_gap: float
    change: float


class VersionPost(Strict):
    name: str = Field(min_length=1, max_length=255)
    note: str = ""


class VersionOut(BaseModel):
    id: int
    name: str
    note: str
    author: str
    created_at: datetime
    staged_count: int


class AuditOut(BaseModel):
    id: int
    review_ref: str | None
    action: str
    detail: str
    username: str
    created_at: datetime


class PrestagingPatch(Strict):
    changes: dict[str, str | None]


class ReferenceEntry(Strict):
    code: str
    label: str | None = None


class ReferencePut(Strict):
    taxonomy: list[ReferenceEntry] | None = None
    business: list[ReferenceEntry] | None = None
    location: list[ReferenceEntry] | None = None

"""Reviews and the plan state attached to them."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.constants import ApprovalRoute, ApprovalStatus, EffortSize, Origin, Quarter
from app.models.base import Base, JSONType, TimestampMixin
from app.models.org import AssuranceFunction, SubTeam


class Plan(Base, TimestampMixin):
    __tablename__ = "plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="Draft")

    reviews: Mapped[list["Review"]] = relationship(back_populates="plan")


class Review(Base, TimestampMixin):
    """A candidate or committed assurance review.

    The four factor scores live on `ReviewScore`, not here, because they are facts
    restated by the scoring engine rather than attributes a planner maintains (rule 1).
    """

    __tablename__ = "review"
    __table_args__ = (UniqueConstraint("plan_id", "ref", name="uq_review_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), nullable=False, index=True)
    ref: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    origin: Mapped[Origin] = mapped_column(String(40), nullable=False)
    #: Regulator-mandated. Always implies origin == Regulatory Assurance (rule 4).
    mandated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    taxonomy_code: Mapped[str | None] = mapped_column(String(120))
    assurance_function_id: Mapped[int] = mapped_column(
        ForeignKey("assurance_function.id"), nullable=False, index=True
    )
    sub_team_id: Mapped[int | None] = mapped_column(ForeignKey("sub_team.id"))
    business: Mapped[str | None] = mapped_column(String(255))

    effort_size: Mapped[EffortSize] = mapped_column(String(1), nullable=False, default=EffortSize.M)
    #: Independently editable per review; beats the size default (rule 7).
    fte_override: Mapped[int | None] = mapped_column(Integer)

    regulator: Mapped[str | None] = mapped_column(String(120))
    regulation: Mapped[str | None] = mapped_column(String(500))
    rris_ids: Mapped[str | None] = mapped_column(String(500))
    rca_linked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    go_live: Mapped[date | None] = mapped_column(Date)

    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    plan: Mapped[Plan] = relationship(back_populates="reviews")
    assurance_function: Mapped[AssuranceFunction] = relationship(lazy="selectin")
    sub_team: Mapped[SubTeam | None] = relationship(lazy="selectin")
    locations: Mapped[list["ReviewLocation"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin"
    )
    scores: Mapped[list["ReviewScore"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin",
        order_by="ReviewScore.as_at.desc()",
    )
    item: Mapped["PlanItem"] = relationship(
        back_populates="review", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    prestaging: Mapped["HeliosPrestaging"] = relationship(
        back_populates="review", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin"
    )
    steward: Mapped["StewardConsultation"] = relationship(
        back_populates="review", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    notes: Mapped[list["ReviewNote"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin",
        order_by="ReviewNote.created_at.desc()",
    )

    @property
    def rris_list(self) -> list[str]:
        raw = self.rris_ids or ""
        return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]


class ReviewLocation(Base):
    """Locations are multi-value: a review may span markets (rule 13)."""

    __tablename__ = "review_location"
    __table_args__ = (UniqueConstraint("review_id", "location", name="uq_review_location"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review: Mapped[Review] = relationship(back_populates="locations")


class ReviewScore(Base):
    """The four factor scores as at a point in time.

    Insert-only: the scoring engine restates, it never edits, and no API path writes
    these from user input (rule 1).
    """

    __tablename__ = "review_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk: Mapped[float] = mapped_column(Float, nullable=False)
    urgency: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_gap: Mapped[float] = mapped_column(Float, nullable=False)
    change: Mapped[float] = mapped_column(Float, nullable=False)
    as_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="scoring-engine")

    review: Mapped[Review] = relationship(back_populates="scores")


class PlanItem(Base, TimestampMixin):
    """Planner-owned state for one review.

    The computed priority is never written here -- only the override, beside it, with
    the rationale that justifies it (rule 3).
    """

    __tablename__ = "plan_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    staged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    planned_quarter: Mapped[Quarter | None] = mapped_column(String(2))
    priority_override: Mapped[float | None] = mapped_column(Float)
    priority_override_rationale: Mapped[str | None] = mapped_column(Text)
    descope_rationale: Mapped[str | None] = mapped_column(Text)
    #: Optimistic concurrency -- the prototype was single-user, this is not (risk R2).
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    review: Mapped[Review] = relationship(back_populates="item")


class HeliosPrestaging(Base, TimestampMixin):
    """The Helios pre-staging attributes, held as the spec's field set.

    Stored as a document because the field set is owned by the Helios Planning Key
    Fields spec, not by this application -- a spec change should not need a migration.
    Derived fields are never stored; they are computed from Target Start Date on read.
    """

    __tablename__ = "helios_prestaging"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    values: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    target_start: Mapped[date | None] = mapped_column(Date)

    review: Mapped[Review] = relationship(back_populates="prestaging")


class Approval(Base, TimestampMixin):
    """One gate per review, routed by type (rule 10)."""

    __tablename__ = "approval"
    __table_args__ = (UniqueConstraint("review_id", "gate", name="uq_approval_gate"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, index=True
    )
    route: Mapped[ApprovalRoute] = mapped_column(String(20), nullable=False)
    gate: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.PENDING
    )
    approver: Mapped[str | None] = mapped_column(String(120))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)

    review: Mapped[Review] = relationship(back_populates="approvals")


class StewardConsultation(Base):
    """Rule 14 -- who the risk steward was, who recorded it, and when."""

    __tablename__ = "steward_consultation"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    steward_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    review: Mapped[Review] = relationship(back_populates="steward")


class ReviewNote(Base):
    """The per-review decision log the prototype keeps in the Risk Radar drawer."""

    __tablename__ = "review_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    review: Mapped[Review] = relationship(back_populates="notes")

"""Weights, audit trail and plan versions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin


class PriorityWeight(Base, TimestampMixin):
    """The a/b/c/d weights, versioned per plan so past decisions stay explicable."""

    __tablename__ = "priority_weight"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), nullable=False, index=True)
    a_risk: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    b_urgency: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    c_coverage_gap: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    d_change: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    set_by: Mapped[str] = mapped_column(String(120), nullable=False)


class AuditEntry(Base):
    """Append-only.

    Rule 11: there is no update or delete path to this table anywhere in the
    application, and the prototype's "Clear log" action is deliberately absent
    (decision D3).
    """

    __tablename__ = "audit_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("review.id", ondelete="SET NULL"), index=True
    )
    review_ref: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class PlanVersion(Base):
    """A named snapshot of the whole plan state, restorable in full (rule 12).

    The audit trail is not part of the snapshot and is never rolled back -- restoring a
    version is itself an audited event.
    """

    __tablename__ = "plan_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    staged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

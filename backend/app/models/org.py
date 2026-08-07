"""Assurance functions, sub-teams and reference data.

In production the reference lists come from the Helios KBD reference-data mapper; these
tables are the local projection of that feed and the admin fallback behind it.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.constants import ReferenceKind
from app.models.base import Base, TimestampMixin


class AssuranceFunction(Base, TimestampMixin):
    __tablename__ = "assurance_function"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    #: Rule 8 -- capacity is FTE per quarter per assurance function.
    fte_per_quarter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Replaces the prototype's roster-derived "staffed teams" (decision D2).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sub_teams: Mapped[list["SubTeam"]] = relationship(
        back_populates="assurance_function", cascade="all, delete-orphan"
    )


class SubTeam(Base, TimestampMixin):
    __tablename__ = "sub_team"
    __table_args__ = (UniqueConstraint("assurance_function_id", "name", name="uq_sub_team_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assurance_function_id: Mapped[int] = mapped_column(
        ForeignKey("assurance_function.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    assurance_function: Mapped[AssuranceFunction] = relationship(back_populates="sub_teams")


class ReferenceData(Base, TimestampMixin):
    """Risk taxonomy L3, business and location lists.

    Taxonomy carries a stable `code` because it is what is stored against a review; the
    label may change freely. Retiring a value deactivates it rather than deleting it, so
    reviews still referencing it keep displaying (risk R1).
    """

    __tablename__ = "reference_data"
    __table_args__ = (UniqueConstraint("kind", "code", name="uq_reference_kind_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[ReferenceKind] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

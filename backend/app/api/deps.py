"""Shared route dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_session
from app.models import Plan, Review


def get_plan(session: Session = Depends(get_session)) -> Plan:
    plan = session.query(Plan).filter(Plan.year == settings.plan_year).one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No plan for {settings.plan_year}. Run the seed first.",
        )
    return plan


def get_review(ref: str, session: Session = Depends(get_session),
               plan: Plan = Depends(get_plan)) -> Review:
    review = (
        session.query(Review).filter(Review.plan_id == plan.id, Review.ref == ref).one_or_none()
    )
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No review {ref!r}.")
    return review

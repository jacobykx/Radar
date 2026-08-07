from __future__ import annotations

import pytest

from app.domain.constants import EffortSize, Origin, Quarter
from app.domain.types import FunctionCapacity, ReviewView, Scores, Weights


@pytest.fixture
def weights() -> Weights:
    return Weights()


def make_review(
    ref: str = "1.1",
    *,
    mandated: bool = False,
    origin: Origin | None = None,
    function: str = "Financial Crime Assurance",
    size: EffortSize = EffortSize.M,
    scores: tuple[float, float, float, float] = (4, 4, 4, 4),
    staged: bool = True,
    quarter: Quarter | None = None,
    **kwargs,
) -> ReviewView:
    """A review with sane defaults; override only what the test is about."""
    if origin is None:
        origin = Origin.REGULATORY if mandated else Origin.RADAR
    risk, urgency, coverage, change = scores
    return ReviewView(
        ref=ref,
        title=f"Review {ref}",
        origin=origin,
        mandated=mandated,
        assurance_function=function,
        effort_size=size,
        scores=Scores(risk=risk, urgency=urgency, coverage_gap=coverage, change=change),
        staged=staged,
        planned_quarter=quarter,
        **kwargs,
    )


@pytest.fixture
def review_factory():
    return make_review


@pytest.fixture
def capacity() -> FunctionCapacity:
    return FunctionCapacity(name="Financial Crime Assurance", fte_per_quarter=10)

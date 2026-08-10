"""Capacity.

Rule 7: effort size S/M/L requires 2/3/4 FTE by default; a per-review FTE overrides it.

Rule 8: capacity is FTE per quarter per assurance function. A review scheduled in a
quarter draws its FTE for that quarter, concurrently with everything else in it.
Mandated demand commits capacity first; the rest fills what remains.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .constants import QUARTERS, Quarter
from .types import FunctionCapacity, Review


@dataclass(frozen=True)
class QuarterLoad:
    quarter: Quarter
    capacity: int
    demand: int

    @property
    def headroom(self) -> int:
        return self.capacity - self.demand

    @property
    def over(self) -> bool:
        return self.demand > self.capacity

    def to_dict(self) -> dict:
        return {
            "quarter": self.quarter.value,
            "capacity": self.capacity,
            "demand": self.demand,
            "headroom": self.headroom,
            "over": self.over,
        }


@dataclass(frozen=True)
class FunctionLoad:
    function: str
    fte_per_quarter: int
    quarters: tuple[QuarterLoad, ...]
    unscheduled_fte: int

    @property
    def over(self) -> bool:
        return any(q.over for q in self.quarters)

    def to_dict(self) -> dict:
        return {
            "function": self.function,
            "fte_per_quarter": self.fte_per_quarter,
            "quarters": [q.to_dict() for q in self.quarters],
            "unscheduled_fte": self.unscheduled_fte,
            "over": self.over,
        }


@dataclass(frozen=True)
class BottomUpFill:
    """Mandated demand committed first, the remainder available to everything else."""

    annual_fte_quarters: int
    mandated_fte: int
    additional_fte: int

    @property
    def remaining_after_mandated(self) -> int:
        return self.annual_fte_quarters - self.mandated_fte

    @property
    def headroom(self) -> int:
        return self.remaining_after_mandated - self.additional_fte

    @property
    def over(self) -> bool:
        return self.headroom < 0

    def to_dict(self) -> dict:
        return {
            "annual_fte_quarters": self.annual_fte_quarters,
            "mandated_fte": self.mandated_fte,
            "additional_fte": self.additional_fte,
            "remaining_after_mandated": self.remaining_after_mandated,
            "headroom": self.headroom,
            "over": self.over,
        }


def quarter_demand(reviews: Iterable[Review], function: str, quarter: Quarter) -> int:
    """FTE drawn from one function in one quarter by the reviews in the plan."""
    return sum(
        r.fte
        for r in reviews
        if r.in_plan and r.assurance_function == function and r.planned_quarter == quarter
    )


def function_load(reviews: Iterable[Review], capacity: FunctionCapacity) -> FunctionLoad:
    reviews = list(reviews)
    quarters = tuple(
        QuarterLoad(
            quarter=q,
            capacity=capacity.fte_per_quarter,
            demand=quarter_demand(reviews, capacity.name, q),
        )
        for q in QUARTERS
    )
    unscheduled = sum(
        r.fte
        for r in reviews
        if r.in_plan and r.assurance_function == capacity.name and r.planned_quarter is None
    )
    return FunctionLoad(
        function=capacity.name,
        fte_per_quarter=capacity.fte_per_quarter,
        quarters=quarters,
        unscheduled_fte=unscheduled,
    )


def bottom_up_fill(
    reviews: Iterable[Review], capacities: Iterable[FunctionCapacity]
) -> BottomUpFill:
    reviews = list(reviews)
    annual = sum(c.annual_fte_quarters for c in capacities if c.is_active)
    planned = [r for r in reviews if r.in_plan]
    return BottomUpFill(
        annual_fte_quarters=annual,
        mandated_fte=sum(r.fte for r in planned if r.mandated),
        additional_fte=sum(r.fte for r in planned if not r.mandated),
    )

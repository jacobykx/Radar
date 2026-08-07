"""Waterfall scheduling.

Rule 9: auto-fill packs Q1 -> Q4, placing each review in the *earliest* quarter with
remaining FTE, mandated first and then by priority. A team's quarterly FTE is never
exceeded; anything that cannot fit is left unscheduled and flagged.

Mandated reviews that already hold a quarter -- derived from the regulatory go-live date
-- keep it and commit their capacity before anything else is placed. They are pinned by
an external obligation, so the scheduler works around them rather than moving them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.domain.constants import QUARTERS, Quarter
from app.domain.scoring import sort_key
from app.domain.types import FunctionCapacity, ReviewView, Weights


@dataclass
class Placement:
    ref: str
    function: str
    quarter: Quarter | None
    fte: int
    moved: bool


@dataclass
class WaterfallResult:
    placed: list[Placement] = field(default_factory=list)
    unplaced: list[Placement] = field(default_factory=list)
    #: Final quarter per review ref, including the pinned ones that were left alone.
    quarters: dict[str, Quarter | None] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        moved = len([p for p in self.placed if p.moved])
        text = f"Waterfall Q1->Q4: {moved} scheduled"
        if self.unplaced:
            text += f", {len(self.unplaced)} could not fit"
        return text


def _pinned(review: ReviewView) -> bool:
    """A mandated review already sitting in a quarter holds that slot."""
    return review.mandated and review.planned_quarter is not None


def waterfall(
    reviews: Iterable[ReviewView],
    capacities: Sequence[FunctionCapacity],
    weights: Weights,
) -> WaterfallResult:
    """Schedule every in-plan review, one assurance function at a time.

    Pure: nothing is mutated. The caller persists `result.quarters`.
    """
    reviews = [r for r in reviews if r.in_plan]
    result = WaterfallResult()

    for capacity in capacities:
        if not capacity.is_active:
            continue
        mine = [r for r in reviews if r.assurance_function == capacity.name]
        if not mine:
            continue

        load: dict[Quarter, int] = {q: 0 for q in QUARTERS}

        for review in mine:
            if _pinned(review):
                load[review.planned_quarter] += review.fte
                result.quarters[review.ref] = review.planned_quarter

        queue = sorted((r for r in mine if not _pinned(r)), key=lambda r: sort_key(r, weights))

        for review in queue:
            fte = review.fte
            target = next(
                (q for q in QUARTERS if load[q] + fte <= capacity.fte_per_quarter),
                None,
            )
            placement = Placement(
                ref=review.ref,
                function=capacity.name,
                quarter=target,
                fte=fte,
                moved=target != review.planned_quarter,
            )
            if target is None:
                result.unplaced.append(placement)
            else:
                load[target] += fte
                result.placed.append(placement)
            result.quarters[review.ref] = target

    return result

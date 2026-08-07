"""Priority scoring.

Rule 2: priority = (a·risk + b·urgency + c·coverage_gap + d·change) / (a+b+c+d), so the
result stays on the 1-5 scale whatever the weights.

Rule 3: a user may override the computed priority, but the computed value is never
overwritten -- both are stored, and an override without a rationale is refused.

Rule 5: mandated reviews are not driver-scored at all.
"""

from __future__ import annotations

from app.domain.constants import BAND_FLOOR, Band
from app.domain.errors import RationaleRequired
from app.domain.types import ReviewView, Scores, Weights

PRIORITY_MIN = 0.0
PRIORITY_MAX = 5.0


def computed_priority(scores: Scores, weights: Weights) -> float:
    """The weighted priority, normalised by the sum of the weights.

    With every weight at zero the numerator is zero too, so the fallback denominator of
    1 yields 0.0 rather than a division error.
    """
    total = weights.total or 1.0
    weighted = (
        scores.risk * weights.risk
        + scores.urgency * weights.urgency
        + scores.coverage_gap * weights.coverage_gap
        + scores.change * weights.change
    )
    return weighted / total


def effective_priority(review: ReviewView, weights: Weights) -> float | None:
    """The priority in force: the override if one is set, else the computed value.

    Mandated reviews are pinned and not driver-scored, so they have no priority.
    """
    if review.mandated:
        return None
    if review.priority_override is not None:
        return review.priority_override
    if review.scores is None:
        return None
    return computed_priority(review.scores, weights)


def band(value: float) -> Band:
    for floor, name in BAND_FLOOR:
        if value >= floor:
            return name
    return Band.LOW


def band_of(review: ReviewView, weights: Weights) -> Band:
    """Mandated reviews show "Mandated" in place of a priority band (rule 5)."""
    if review.mandated:
        return Band.MANDATED
    value = effective_priority(review, weights)
    return Band.LOW if value is None else band(value)


def validate_override(value: float, rationale: str | None) -> tuple[float, str]:
    """Check an override before it is stored. A rationale is mandatory (rule 3)."""
    text = (rationale or "").strip()
    if not text:
        raise RationaleRequired("A rationale is required to override the computed priority.")
    clamped = min(PRIORITY_MAX, max(PRIORITY_MIN, float(value)))
    return clamped, text


def sort_key(review: ReviewView, weights: Weights) -> tuple[int, float]:
    """Rank for any priority-ordered list: mandated first, then priority descending."""
    priority = effective_priority(review, weights) or 0.0
    return (0 if review.mandated else 1, -priority)

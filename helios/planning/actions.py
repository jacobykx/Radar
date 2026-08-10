"""Every change a planner can make, and the audit entry it leaves.

One place for the mutations so that no change to the plan can happen without being
recorded (rule 11). The rules themselves live in the modules alongside this one — these
functions apply them, write the audit line, and nothing else.

Each takes the loaded `Plan`, mutates it in place, and leaves saving to the caller's
`Store.mutate()` block.
"""

from __future__ import annotations

from .. import reference as refdata
from . import prestaging, scheduling, scoring, staging
from .constants import (
    DRIVERS,
    QUARTERS,
    ApprovalStatus,
    Band,
    EffortSize,
    Origin,
    Quarter,
)
from .errors import PlanningError
from .store import Plan, now
from .types import Approval, Comment, Review, Scores, Weights

#: Bands that "stage all the obvious ones" covers (prototype: Critical + High).
_BULK_BANDS = (Band.CRITICAL, Band.HIGH)


# --------------------------------------------------------------------------- weights


def set_weights(plan: Plan, values: dict, *, user: str) -> Weights:
    """Weights are the planner's only lever on priority; the scores are read-only facts."""
    before = plan.weights
    plan.weights = Weights.from_dict({**before.to_dict(), **(values or {})})
    changed = [
        f"{k} {getattr(before, k):g}→{getattr(plan.weights, k):g}"
        for k in ("risk", "urgency", "coverage_gap", "change")
        if getattr(before, k) != getattr(plan.weights, k)
    ]
    if changed:
        plan.log(user, "Weights changed", ", ".join(changed))
    return plan.weights


def reset_weights(plan: Plan, *, user: str) -> Weights:
    plan.weights = Weights()
    plan.log(user, "Weights reset", "equal weighting")
    return plan.weights


# --------------------------------------------------------------------------- staging


def stage(plan: Plan, ref: str, *, user: str) -> Review:
    review = plan.review(ref)
    if review.staged:
        return review
    review.staged = True
    review.descope_rationale = ""  # back in scope; the old reason no longer applies
    plan.log(user, "Staged into the plan", review.title, ref=ref)
    return review


def unstage(plan: Plan, ref: str, *, user: str) -> Review:
    """Take a review out of the plan straight away, reason to follow.

    The prototype un-stages on the click and chases the rationale afterwards, flagging the
    review until one is recorded. Refusing the click instead would stop a planner shaping
    the plan at the speed they think. The rule still bites, just later: an outstanding
    rationale is counted on the dashboard, badged on the Risk Radar tab, and listed on the
    shaped plan, so nothing leaves the plan quietly.
    """
    review = plan.review(ref)
    if not review.staged:
        return review
    review.staged = False
    review.planned_quarter = None
    detail = review.descope_rationale or "reason pending"
    plan.log(user, "Staged OUT", detail, ref=ref)
    return review


def set_reason(plan: Plan, ref: str, rationale: str, *, user: str) -> Review:
    """Record why a review is out of the plan. This is what clears the outstanding flag."""
    review = plan.review(ref)
    text = (rationale or "").strip()
    review.descope_rationale = text
    plan.log(user, "Descope rationale" if text else "Descope rationale cleared",
             text or "(cleared)", ref=ref)
    return review


def descope(plan: Plan, ref: str, rationale: str, *, user: str) -> Review:
    """Un-stage and record the reason in one step, for callers that have both."""
    text = staging.validate_descope(rationale)
    unstage(plan, ref, user=user)
    return set_reason(plan, ref, text, user=user)


def stage_critical_and_high(plan: Plan, *, user: str) -> int:
    """Bulk-stage the obvious ones. Descoped reviews are left alone — that was a decision."""
    staged = 0
    for review in plan.reviews:
        if review.staged or review.descoped:
            continue
        if scoring.band_of(review, plan.weights) in _BULK_BANDS:
            review.staged = True
            staged += 1
    plan.log(user, "Bulk staged", f"{staged} review(s) in Critical or High")
    return staged


def clear_staging(plan: Plan, *, user: str) -> int:
    """Clear the plan back to its mandated floor. Mandated reviews cannot leave."""
    cleared = 0
    for review in plan.reviews:
        if review.staged and not review.mandated:
            review.staged = False
            review.planned_quarter = None
            cleared += 1
    plan.log(user, "Staging cleared", f"{cleared} review(s) removed; mandated kept")
    return cleared


# --------------------------------------------------------------------------- priority


def override_priority(plan: Plan, ref: str, value: float, rationale: str, *, user: str) -> Review:
    """Rule 3: the computed value is kept; the override sits beside it, with its reason."""
    review = plan.review(ref)
    clamped, text = scoring.validate_override(value, rationale)
    computed = scoring.computed_priority(review.scores, plan.weights) if review.scores else None
    review.priority_override = clamped
    review.priority_rationale = text
    detail = f"{clamped:.2f}" + (f" (computed {computed:.2f})" if computed is not None else "")
    plan.log(user, "Priority overridden", f"{detail} — {text}", ref=ref)
    return review


def set_score(plan: Plan, ref: str, driver: str, value: float, *, user: str) -> Review:
    """Edit one of the four driver scores in place, as the prototype's table allows.

    The scores come from a scoring engine, so an edit here is a deliberate departure from
    it. The original is kept on `seeded_scores` so the divergence stays visible and can be
    reset, and every edit lands on the audit trail.
    """
    review = plan.review(ref)
    if review.scores is None:
        raise PlanningError(f"{ref} is not driver-scored, so its scores cannot be edited.")
    if driver not in ("risk", "urgency", "coverage_gap", "change"):
        raise PlanningError(f"{driver!r} is not one of the four drivers.")

    clamped = min(5.0, max(1.0, float(value)))
    before = getattr(review.scores, driver)
    if clamped == before:
        return review
    if review.seeded_scores is None:
        review.seeded_scores = review.scores  # first edit pins what the engine said

    from dataclasses import replace as _replace
    review.scores = _replace(review.scores, **{driver: clamped})
    label = dict(DRIVERS)[driver]
    plan.log(user, "Score edited", f"{label} {before:g} → {clamped:g}", ref=ref)
    return review


def reset_scores(plan: Plan, ref: str, *, user: str) -> Review:
    """Put the driver scores back to what the scoring engine supplied."""
    review = plan.review(ref)
    if review.seeded_scores is None:
        return review
    review.scores = review.seeded_scores
    review.seeded_scores = None
    plan.log(user, "Scores reset", "back to the scoring engine's values", ref=ref)
    return review


def set_business(plan: Plan, ref: str, value: str, *, user: str) -> Review:
    """Business is edited in the Risk Radar row and flows through to the Helios column."""
    review = plan.review(ref)
    text = (value or "").strip()
    if text:
        canonical, ok = refdata.normalise(text, tuple(plan.reference.get("business", ())))
        if not ok:
            raise PlanningError(f"{text!r} is not in the business reference list.")
        text = canonical
    review.business = text
    review.helios["business"] = text
    plan.log(user, "Business changed", text or "(cleared)", ref=ref)
    return review


def clear_override(plan: Plan, ref: str, *, user: str) -> Review:
    review = plan.review(ref)
    review.priority_override = None
    review.priority_rationale = ""
    plan.log(user, "Priority override removed", "back to the computed value", ref=ref)
    return review


# --------------------------------------------------------------------- effort & quarter


def set_effort(plan: Plan, ref: str, size: str, *, user: str) -> Review:
    review = plan.review(ref)
    before = review.effort_size
    review.effort_size = EffortSize(size)
    plan.log(user, "Effort size changed", f"{before.value} → {review.effort_size.value}", ref=ref)
    return review


def set_fte(plan: Plan, ref: str, fte: int | None, *, user: str) -> Review:
    """A per-review FTE that beats the size default (rule 7). None restores the default."""
    review = plan.review(ref)
    review.fte_override = int(fte) if fte is not None else None
    detail = f"{review.fte} FTE" + ("" if fte is not None else " (back to the size default)")
    plan.log(user, "FTE changed", detail, ref=ref)
    return review


def set_quarter(plan: Plan, ref: str, quarter: str | None, *, user: str) -> Review:
    review = plan.review(ref)
    review.planned_quarter = Quarter(quarter) if quarter else None
    plan.log(user, "Quarter set", review.planned_quarter.value if review.planned_quarter
             else "(unscheduled)", ref=ref)
    return review


def waterfall(plan: Plan, *, user: str) -> dict:
    """Rule 9: pack Q1 → Q4, mandated first, never exceeding a function's quarterly FTE."""
    result = scheduling.waterfall(plan.reviews, plan.capacities, plan.weights)
    for ref, quarter in result.quarters.items():
        plan.review(ref).planned_quarter = quarter
    plan.log(user, "Quarters auto-filled", result.summary)
    return {
        "placed": len(result.placed),
        "unplaced": [p.ref for p in result.unplaced],
        "summary": result.summary,
    }


def clear_quarters(plan: Plan, *, user: str) -> int:
    """Mandated reviews keep theirs — the go-live date decides, not the scheduler."""
    cleared = 0
    for review in plan.reviews:
        if review.planned_quarter and not review.mandated:
            review.planned_quarter = None
            cleared += 1
    plan.log(user, "Quarters cleared", f"{cleared} review(s); mandated kept")
    return cleared


def set_capacity(plan: Plan, function: str, fte_per_quarter: int, *, user: str) -> None:
    from .types import FunctionCapacity

    fte = max(0, int(fte_per_quarter))
    plan.capacities = [
        FunctionCapacity(name=c.name, fte_per_quarter=fte if c.name == function
                         else c.fte_per_quarter)
        for c in plan.capacities
    ]
    plan.log(user, "Capacity changed", f"{function}: {fte} FTE per quarter")


# --------------------------------------------------------------------------- the backlog


def add_review(plan: Plan, data: dict, *, user: str) -> Review:
    """File a new candidate. Mandated ones are pinned into the plan; risk-led ones queue.

    Rule 4 is enforced by construction: the origin follows the mandated flag rather than
    being accepted from the caller, so the two cannot disagree.
    """
    title = (data.get("title") or "").strip()
    if not title:
        raise PlanningError("A review needs a title.")
    rationale = (data.get("rationale") or "").strip()
    if not rationale:
        raise PlanningError("A rationale is required — it is what the plan is defended with.")

    function = (data.get("assurance_function") or "").strip()
    if not function:
        raise PlanningError("A review needs an assurance function.")

    mandated = bool(data.get("mandated"))
    origin = Origin.REGULATORY if mandated else Origin.RISK
    staging.validate_origin(origin, mandated)

    go_live = prestaging.parse_go_live(data.get("go_live"))
    scores = data.get("scores") or {}

    review = Review(
        ref=plan.next_ref("EXT" if mandated else "RSK"),
        title=title,
        assurance_function=function,
        origin=origin,
        mandated=mandated,
        effort_size=EffortSize(data.get("effort_size") or "M"),
        # Mandated reviews are pinned regardless of score, so they are not driver-scored.
        scores=None if mandated else Scores(
            risk=float(scores.get("risk", 3)),
            urgency=float(scores.get("urgency", 3)),
            coverage_gap=float(scores.get("coverage_gap", 3)),
            change=float(scores.get("change", 3)),
        ),
        sub_team=(data.get("sub_team") or "").strip(),
        taxonomy_code=(data.get("taxonomy_code") or "").strip(),
        business=(data.get("business") or "").strip(),
        locations=list(data.get("locations") or []),
        regulator=(data.get("regulator") or "").strip(),
        regulation=(data.get("regulation") or "").strip(),
        rris_ids=[i.strip() for i in str(data.get("rris_ids") or "").replace(",", ";").split(";")
                  if i.strip()],
        go_live=go_live,
        staged=mandated,
        planned_quarter=prestaging.quarter_of(go_live) if mandated else None,
        comments=[Comment(at=now(), user=user or "Unattributed", text=f"[Rationale] {rationale}")],
    )
    review.helios = prestaging.seed_values(review)
    review.helios["reviewDetail"] = rationale
    review.helios["scopeRationale"] = rationale

    plan.reviews.append(review)
    plan.log(user, "Review added",
             f"{'Regulatory' if mandated else 'Risk-led'}: {title} — {rationale}", ref=review.ref)
    return review


def remove_review(plan: Plan, ref: str, *, user: str) -> None:
    """Only ever a review someone added here. Seeded candidates are descoped, not deleted."""
    review = plan.review(ref)
    if not review.ref.startswith(("EXT-", "RSK-")):
        raise PlanningError(
            f"{ref} came from the candidate list and cannot be deleted — descope it instead, "
            "so the audit trail keeps the reason."
        )
    plan.reviews = [r for r in plan.reviews if r.ref != ref]
    plan.log(user, "Review deleted", review.title, ref=ref)


def add_comment(plan: Plan, ref: str, text: str, *, user: str) -> Comment:
    body = (text or "").strip()
    if not body:
        raise PlanningError("An empty note is not worth recording.")
    review = plan.review(ref)
    comment = Comment(at=now(), user=user or "Unattributed", text=body)
    review.comments.append(comment)
    plan.log(user, "Note added", body, ref=ref)
    return comment


def set_steward(plan: Plan, ref: str, name: str, consulted: bool, *, user: str) -> Review:
    """Risk-radar candidates carry whether the risk steward has been consulted."""
    review = plan.review(ref)
    review.steward_consulted = bool(consulted)
    review.steward_name = (name or "").strip()
    plan.log(user, "Risk steward consultation",
             f"{review.steward_name or 'unnamed'}" if consulted else "cleared", ref=ref)
    return review


def set_locations(plan: Plan, ref: str, locations: list[str], *, user: str) -> Review:
    """Locations are multi-value and normalised against the reference list."""
    review = plan.review(ref)
    joined, unknown = refdata.normalise_many("; ".join(locations), refdata.LOCATIONS)
    review.locations = [loc for loc in joined.split("; ") if loc]
    review.helios["location"] = joined
    detail = joined or "(none)"
    if unknown:
        detail += f" — not in the reference list: {', '.join(unknown)}"
    plan.log(user, "Locations changed", detail, ref=ref)
    return review


# --------------------------------------------------------------------------- approval


def sign_off(plan: Plan, ref: str, decision: str, note: str, *, user: str) -> Review:
    """Rule 10: one gate, one decision. Returning it needs a reason on record."""
    from .approval import gate_of, validate_decision

    review = plan.review(ref)
    status = ApprovalStatus(decision)
    text = validate_decision(status, note)
    review.approval = Approval(status=status, by=user or "Unattributed", at=now(), note=text)
    plan.log(user, f"{status.value} at {gate_of(review)}", text or review.title, ref=ref)
    return review


# --------------------------------------------------------------- Helios pre-staging


def update_prestaging(plan: Plan, ref: str, changes: dict, *, user: str) -> Review:
    review = plan.review(ref)
    applied = prestaging.apply(review, changes)
    for key, value in applied.items():
        plan.log(user, "Pre-staging edit", f"{key} → {value or '(cleared)'}", ref=ref)
    return review


# -------------------------------------------------------------------- reference data


def set_reference(plan: Plan, kind: str, values: list, *, user: str) -> list:
    """Replace a reference list. Values in use are not removed from reviews that carry them.

    A review keeps whatever it was given; the pre-staging validation then reports the value
    as unrecognised, which is the visible, fixable outcome rather than a silent edit.
    """
    if kind not in ("taxonomy", "business", "location"):
        raise PlanningError(f"{kind!r} is not a reference list.")
    plan.reference[kind] = values
    plan.log(user, "Reference data updated", f"{kind}: {len(values)} value(s)")
    return values


def quarters() -> list[str]:
    return [q.value for q in QUARTERS]

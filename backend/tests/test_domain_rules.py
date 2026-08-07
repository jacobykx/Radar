"""The methodology, as executable rules.

Every test here maps to a numbered rule in BUILD_INSTRUCTIONS section 2. These exist so a
later refactor cannot quietly break the assurance methodology -- if one of them fails,
the change is wrong, not the test.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from app.domain import approval, helios, scheduling, scoring, staging
from app.domain import capacity as cap
from app.domain.constants import (
    SIZE_DAYS,
    SIZE_FTE,
    ApprovalRoute,
    ApprovalStatus,
    Band,
    EffortSize,
    Origin,
    Quarter,
)
from app.domain.errors import CommentRequired, OriginConflict, RationaleRequired
from app.domain.types import FunctionCapacity, Scores, Weights
from tests.conftest import make_review

# ----------------------------------------------------------------- rule 1: read-only scores


def test_factor_scores_are_facts_not_inputs():
    """Rule 1. The four scores are supplied by the scoring engine.

    They are absent from every write schema, so there is no code path that edits them.
    This test pins the shape: `Scores` is frozen, and the request models carry no score
    fields for a caller to smuggle one through.
    """
    scores = Scores(risk=4, urgency=3, coverage_gap=2, change=1)
    with pytest.raises(FrozenInstanceError):
        scores.risk = 5  # type: ignore[misc]


# ----------------------------------------------------------------- rule 2: weighted priority


def test_priority_is_normalised_by_the_weight_sum(weights):
    """Rule 2. Weights change the emphasis, never the scale."""
    scores = Scores(risk=5, urgency=1, coverage_gap=1, change=1)
    heavy_on_risk = Weights(risk=3, urgency=1, coverage_gap=1, change=1)

    assert scoring.computed_priority(scores, weights) == pytest.approx(2.0)
    assert scoring.computed_priority(scores, heavy_on_risk) == pytest.approx(3.0)
    # whatever the weights, the result stays inside the 1-5 input range
    for w in (weights, heavy_on_risk, Weights(risk=0, urgency=0, coverage_gap=0, change=7)):
        assert 1 <= scoring.computed_priority(Scores(3, 3, 3, 3), w) <= 5


def test_equal_weights_give_the_plain_mean(weights):
    assert scoring.computed_priority(Scores(4, 3, 2, 1), weights) == pytest.approx(2.5)


def test_all_zero_weights_do_not_divide_by_zero():
    zero = Weights(risk=0, urgency=0, coverage_gap=0, change=0)
    assert scoring.computed_priority(Scores(4, 4, 4, 4), zero) == 0.0


def test_bands_sit_on_the_documented_thresholds():
    assert scoring.band(4.3) is Band.CRITICAL
    assert scoring.band(4.29) is Band.HIGH
    assert scoring.band(3.7) is Band.HIGH
    assert scoring.band(3.0) is Band.MEDIUM
    assert scoring.band(2.99) is Band.LOW


# ----------------------------------------------------------------- rule 3: priority override


def test_override_without_a_rationale_is_refused():
    """Rule 3. The rationale is what makes an override auditable, so it is mandatory."""
    with pytest.raises(RationaleRequired):
        scoring.validate_override(4.5, "")
    with pytest.raises(RationaleRequired):
        scoring.validate_override(4.5, "   ")


def test_override_is_stored_beside_the_computed_value_not_over_it(weights):
    """Rule 3. Both values survive, so the divergence stays visible."""
    review = make_review(scores=(2, 2, 2, 2))
    computed = scoring.computed_priority(review.scores, weights)

    value, rationale = scoring.validate_override(4.6, "Board escalation after the Q3 incident")
    review.priority_override = value

    assert computed == pytest.approx(2.0)
    assert scoring.computed_priority(review.scores, weights) == pytest.approx(2.0)
    assert scoring.effective_priority(review, weights) == pytest.approx(4.6)
    assert rationale == "Board escalation after the Q3 incident"


def test_clearing_the_override_restores_the_computed_priority(weights):
    review = make_review(scores=(2, 2, 2, 2), priority_override=4.6)
    review.priority_override = None
    assert scoring.effective_priority(review, weights) == pytest.approx(2.0)


def test_override_is_clamped_to_the_scale():
    assert scoring.validate_override(9.9, "why")[0] == 5.0
    assert scoring.validate_override(-3, "why")[0] == 0.0


# ----------------------------------------------------------------- rules 4-5: mandated reviews


def test_mandated_reviews_are_not_driver_scored(weights):
    """Rule 5. A mandated review is pinned by obligation, so priority does not apply."""
    review = make_review(mandated=True, scores=(5, 5, 5, 5))
    assert scoring.effective_priority(review, weights) is None
    assert scoring.band_of(review, weights) is Band.MANDATED


def test_origin_and_the_mandated_flag_must_agree():
    """Rule 4. Mandated means regulator-mandated, and nothing else claims that origin."""
    staging.validate_origin(Origin.REGULATORY, mandated=True)
    staging.validate_origin(Origin.RISK, mandated=False)
    staging.validate_origin(Origin.RADAR, mandated=False)

    with pytest.raises(OriginConflict):
        staging.validate_origin(Origin.RISK, mandated=True)
    with pytest.raises(OriginConflict):
        staging.validate_origin(Origin.REGULATORY, mandated=False)


# ----------------------------------------------------------------- rule 6: descoping


def test_descoping_without_a_rationale_is_refused():
    """Rule 6, decision D1: the API refuses the state rather than flagging it later."""
    with pytest.raises(RationaleRequired):
        staging.validate_descope(None)
    with pytest.raises(RationaleRequired):
        staging.validate_descope("  ")
    assert (
        staging.validate_descope("  covered by the 2026 thematic  ")
        == "covered by the 2026 thematic"
    )


def test_a_descoped_review_leaves_every_downstream_stage(weights):
    """Rule 6. Staging, capacity, approval, pre-staging and the plan all drop it."""
    kept = make_review("1.1")
    gone = make_review("1.2", staged=False, descope_rationale="merged into 1.1", quarter=Quarter.Q1)
    reviews = [kept, gone]

    assert staging.in_plan(reviews) == [kept]
    assert staging.descoped(reviews) == [gone]
    assert cap.quarter_demand(reviews, kept.assurance_function, Quarter.Q1) == 0
    assert gone not in approval.related_irr(kept, reviews)

    result = scheduling.waterfall(reviews, [FunctionCapacity(kept.assurance_function, 10)], weights)
    assert gone.ref not in result.quarters


def test_unstaged_without_a_rationale_is_reported_not_silently_dropped():
    """The state the API refuses can still arrive by seeding, import or version restore."""
    pending = make_review("1.3", staged=False)
    assert pending.rationale_outstanding is True
    assert pending.descoped is False
    assert staging.outstanding_rationales([pending]) == [pending]


# ----------------------------------------------------------------- rule 7: effort and FTE


def test_effort_sizes_map_to_days_and_default_fte():
    """Rule 7. S/M/L = 60/90/120 days, requiring 2/3/4 FTE."""
    assert [SIZE_DAYS[s] for s in EffortSize] == [60, 90, 120]
    assert [SIZE_FTE[s] for s in EffortSize] == [2, 3, 4]


def test_an_explicit_fte_overrides_the_size_default():
    assert make_review(size=EffortSize.L).fte == 4
    assert make_review(size=EffortSize.L, fte_override=6).fte == 6
    assert make_review(size=EffortSize.S, fte_override=1).fte == 1


# ----------------------------------------------------------------- rule 8: capacity


def test_a_scheduled_review_consumes_its_fte_in_that_quarter(capacity):
    reviews = [
        make_review("1.1", size=EffortSize.L, quarter=Quarter.Q1),   # 4 FTE
        make_review("1.2", size=EffortSize.S, quarter=Quarter.Q1),   # 2 FTE
        make_review("1.3", size=EffortSize.M, quarter=Quarter.Q3),   # 3 FTE
    ]
    load = cap.function_load(reviews, capacity)
    demand = {q.quarter: q.demand for q in load.quarters}

    assert demand == {Quarter.Q1: 6, Quarter.Q2: 0, Quarter.Q3: 3, Quarter.Q4: 0}
    assert load.over is False
    assert next(q for q in load.quarters if q.quarter is Quarter.Q1).headroom == 4


def test_mandated_demand_commits_capacity_before_anything_else(capacity):
    """Rule 8. Headroom is what is left after the obligations are paid for."""
    reviews = [
        make_review("1.1", mandated=True, size=EffortSize.L),   # 4 FTE
        make_review("1.2", size=EffortSize.M),                  # 3 FTE
    ]
    fill = cap.bottom_up_fill(reviews, [capacity])

    assert fill.annual_fte_quarters == 40
    assert fill.mandated_fte == 4
    assert fill.additional_fte == 3
    assert fill.remaining_after_mandated == 36
    assert fill.headroom == 33
    assert fill.over is False


def test_capacity_flags_an_overcommitted_plan():
    small = FunctionCapacity("Financial Crime Assurance", fte_per_quarter=1)
    reviews = [make_review(str(i), size=EffortSize.L) for i in range(3)]
    assert cap.bottom_up_fill(reviews, [small]).over is True


def test_unscheduled_demand_is_reported_separately(capacity):
    reviews = [make_review("1.1", size=EffortSize.L, quarter=None)]
    assert cap.function_load(reviews, capacity).unscheduled_fte == 4


# ----------------------------------------------------------------- rule 9: waterfall


def test_waterfall_fills_the_earliest_quarter_with_room(weights, capacity):
    """Rule 9. Pack Q1 first; only spill forward when the quarter is full."""
    reviews = [make_review(f"1.{i}", size=EffortSize.M) for i in range(1, 5)]  # 3 FTE each, cap 10
    result = scheduling.waterfall(reviews, [capacity], weights)

    assert result.quarters == {
        "1.1": Quarter.Q1, "1.2": Quarter.Q1, "1.3": Quarter.Q1, "1.4": Quarter.Q2,
    }
    assert not result.unplaced


def test_waterfall_never_exceeds_the_quarterly_fte(weights):
    tight = FunctionCapacity("Financial Crime Assurance", fte_per_quarter=4)
    reviews = [make_review(f"1.{i}", size=EffortSize.M) for i in range(1, 6)]  # 3 FTE each
    result = scheduling.waterfall(reviews, [tight], weights)

    for quarter in Quarter:
        assert cap.quarter_demand(
            [r.with_quarter(result.quarters.get(r.ref)) for r in reviews],
            tight.name,
            quarter,
        ) <= tight.fte_per_quarter


def test_waterfall_places_mandated_first_then_by_priority(weights):
    """Rule 9. Obligations before judgement; judgement in priority order."""
    tight = FunctionCapacity("Financial Crime Assurance", fte_per_quarter=3)
    reviews = [
        make_review("low", size=EffortSize.M, scores=(1, 1, 1, 1)),
        make_review("high", size=EffortSize.M, scores=(5, 5, 5, 5)),
        make_review("mand", size=EffortSize.M, mandated=True),
    ]
    result = scheduling.waterfall(reviews, [tight], weights)

    assert result.quarters["mand"] is Quarter.Q1
    assert result.quarters["high"] is Quarter.Q2
    assert result.quarters["low"] is Quarter.Q3


def test_waterfall_leaves_what_cannot_fit_unscheduled_and_flags_it(weights):
    """Rule 9. Overflow is surfaced, never absorbed by over-filling a quarter."""
    tight = FunctionCapacity("Financial Crime Assurance", fte_per_quarter=3)
    reviews = [make_review(f"1.{i}", size=EffortSize.M) for i in range(1, 6)]  # 5 reviews, 4 slots
    result = scheduling.waterfall(reviews, [tight], weights)

    assert len(result.placed) == 4
    assert len(result.unplaced) == 1
    assert result.quarters[result.unplaced[0].ref] is None
    assert "could not fit" in result.summary


def test_a_mandated_review_holds_its_go_live_quarter_through_autofill(weights):
    """A regulatory go-live date is not the scheduler's to move."""
    tight = FunctionCapacity("Financial Crime Assurance", fte_per_quarter=4)
    pinned = make_review("mand", mandated=True, size=EffortSize.M, quarter=Quarter.Q3,
                         go_live=date(2027, 8, 1))
    other = make_review("other", size=EffortSize.M)
    result = scheduling.waterfall([pinned, other], [tight], weights)

    assert result.quarters["mand"] is Quarter.Q3   # untouched
    assert result.quarters["other"] is Quarter.Q1  # filled around it


def test_waterfall_schedules_each_function_against_its_own_capacity(weights):
    functions = [
        FunctionCapacity("Financial Crime Assurance", fte_per_quarter=3),
        FunctionCapacity("Traded Risk Assurance", fte_per_quarter=3),
    ]
    reviews = [
        make_review("fc1", function="Financial Crime Assurance", size=EffortSize.M),
        make_review("fc2", function="Financial Crime Assurance", size=EffortSize.M),
        make_review("tr1", function="Traded Risk Assurance", size=EffortSize.M),
    ]
    result = scheduling.waterfall(reviews, functions, weights)

    assert result.quarters["fc1"] is Quarter.Q1
    assert result.quarters["fc2"] is Quarter.Q2   # FC's Q1 is full
    assert result.quarters["tr1"] is Quarter.Q1   # Traded Risk has its own Q1


def test_waterfall_does_not_mutate_the_reviews_it_is_given(weights, capacity):
    reviews = [make_review("1.1", size=EffortSize.M)]
    scheduling.waterfall(reviews, [capacity], weights)
    assert reviews[0].planned_quarter is None


# ----------------------------------------------------------------- rule 10: sign-off


def test_each_review_has_exactly_one_gate_routed_by_type():
    """Rule 10. One gate, chosen by what the review is -- never several."""
    mandated = make_review("m", mandated=True)
    rca = make_review("r", rca_linked=True)
    standard = make_review("s")

    assert approval.route_of(mandated) is ApprovalRoute.IRR
    assert approval.route_of(rca) is ApprovalRoute.RCA
    assert approval.route_of(standard) is ApprovalRoute.STANDARD
    assert len({approval.gate_of(r) for r in (mandated, rca, standard)}) == 3


def test_a_mandated_rca_linked_review_still_routes_to_irr():
    assert approval.route_of(make_review(mandated=True, rca_linked=True)) is ApprovalRoute.IRR


def test_returning_a_review_requires_a_comment():
    """Rule 10. An approval needs no words; a rejection does."""
    with pytest.raises(CommentRequired):
        approval.validate_decision(ApprovalStatus.RETURNED, "")
    assert (
        approval.validate_decision(ApprovalStatus.RETURNED, "scope too broad") == "scope too broad"
    )
    assert approval.validate_decision(ApprovalStatus.APPROVED, None) == ""


def test_cross_team_linkage_finds_the_same_obligation_elsewhere():
    """The Approval stage must show when another team is assuring the same obligation."""
    mine = make_review("4.1", mandated=True, rris_ids=["RRIS-10421"], regulation="PS7/26")
    same_rris = make_review("9.9", mandated=True, function="Traded Risk Assurance",
                            rris_ids=["RRIS-10421"])
    same_regulation = make_review("8.8", mandated=True, function="Treasury Risk Assurance",
                                  regulation="PS7/26")
    unrelated = make_review("7.7", mandated=True, rris_ids=["RRIS-99999"], regulation="PS1/26")
    not_irr = make_review("6.6", rris_ids=["RRIS-10421"])

    related = approval.related_irr(mine, [mine, same_rris, same_regulation, unrelated, not_irr])
    assert {r.ref for r in related} == {"9.9", "8.8"}


# ----------------------------------------------------------------- Helios pre-staging


def test_plan_and_iap_quarters_are_derived_from_the_target_start_date():
    """Derived, never entered -- so the plan and Helios cannot disagree."""
    assert helios.derived_values(date(2027, 3, 31)) == {
        "planQuarter": "Q1", "iapQuarter": "Q1", "planYear": "2027", "iapYear": "2027",
    }
    assert helios.derived_values(date(2027, 4, 1))["planQuarter"] == "Q2"
    assert helios.derived_values(date(2026, 12, 31)) == {
        "planQuarter": "Q4", "iapQuarter": "Q4", "planYear": "2026", "iapYear": "2026",
    }
    assert helios.derived_values(None)["planQuarter"] == ""


def test_completeness_needs_every_required_field():
    values = {k: "x" for k in helios.REQUIRED_FIELDS}
    assert helios.is_complete(values)

    values["reviewLead"] = "   "
    assert not helios.is_complete(values)
    assert helios.missing_fields(values) == ["reviewLead"]


def test_export_carries_the_spec_field_set_in_order():
    row = helios.export_row({"title": "SS1/23 model risk"}, date(2027, 5, 1))
    assert len(row) == len(helios.EXPORT_HEADER) == 27
    assert row[helios.EXPORT_HEADER.index("Title")] == "SS1/23 model risk"
    assert row[helios.EXPORT_HEADER.index("Plan Quarter")] == "Q2"


# ----------------------------------------------------------------- rule 13: multi-location


def test_a_location_filter_matches_if_any_location_matches():
    """Rule 13. A review may span markets; one hit is enough."""
    review = make_review(locations=["UK", "USA", "Hong Kong"])
    assert "USA" in review.locations
    assert "Germany" not in review.locations

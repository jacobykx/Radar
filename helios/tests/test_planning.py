"""Tests for the planning workflow — the rules, the plan file, and the governance exports.

    python3 -m unittest discover -s helios/tests -t .
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from helios.planning import (
    actions,
    approval,
    capacity,
    exports,
    prestaging,
    scheduling,
    scoring,
    seed,
    staging,
    views,
)
from helios.planning.constants import ApprovalRoute, ApprovalStatus, Band, EffortSize, Quarter
from helios.planning.errors import CommentRequired, NotFound, PlanningError, RationaleRequired
from helios.planning.store import Plan, Store
from helios.planning.types import FunctionCapacity, Review, Scores, Weights


def plan() -> Plan:
    return Plan.seeded()


class Scoring(unittest.TestCase):
    def test_priority_is_normalised_so_it_stays_on_the_one_to_five_scale(self):
        scores = Scores(risk=5, urgency=5, coverage_gap=5, change=5)
        for weights in (Weights(), Weights(risk=3, urgency=0.5, coverage_gap=2, change=1)):
            self.assertAlmostEqual(scoring.computed_priority(scores, weights), 5.0)

    def test_weights_shift_the_ranking(self):
        """The whole point of the weights: what matters most changes what comes first."""
        p = plan()
        change_led = p.review("3.2")   # risk 4, change 5
        risk_led = p.review("5.2")     # risk 5, change 3

        p.weights = Weights(risk=5, urgency=1, coverage_gap=1, change=1)
        self.assertGreater(scoring.effective_priority(risk_led, p.weights),
                           scoring.effective_priority(change_led, p.weights))

        p.weights = Weights(risk=1, urgency=1, coverage_gap=1, change=5)
        self.assertGreater(scoring.effective_priority(change_led, p.weights),
                           scoring.effective_priority(risk_led, p.weights))

    def test_all_zero_weights_do_not_divide_by_zero(self):
        scores = Scores(risk=4, urgency=4, coverage_gap=4, change=4)
        self.assertEqual(scoring.computed_priority(scores, Weights(0, 0, 0, 0)), 0.0)

    def test_bands_fall_on_the_documented_floors(self):
        for value, expected in [(4.3, Band.CRITICAL), (4.29, Band.HIGH), (3.7, Band.HIGH),
                                (3.69, Band.MEDIUM), (3.0, Band.MEDIUM), (2.99, Band.LOW)]:
            self.assertEqual(scoring.band(value), expected, value)

    def test_a_mandated_review_has_no_priority_and_shows_as_mandated(self):
        p = plan()
        mandated = p.review("4.1")
        self.assertIsNone(scoring.effective_priority(mandated, p.weights))
        self.assertEqual(scoring.band_of(mandated, p.weights), Band.MANDATED)

    def test_an_override_replaces_the_computed_value_without_erasing_it(self):
        p = plan()
        actions.override_priority(p, "3.2", 4.9, "Board asked for it early", user="Jacob")
        review = p.review("3.2")
        self.assertEqual(scoring.effective_priority(review, p.weights), 4.9)
        self.assertIsNotNone(review.scores)  # the computed value can still be recomputed
        self.assertEqual(views.review(p, review)["computed_priority"], 4.25)

    def test_an_override_without_a_rationale_is_refused(self):
        p = plan()
        with self.assertRaises(RationaleRequired):
            actions.override_priority(p, "3.2", 4.9, "   ", user="Jacob")
        self.assertIsNone(p.review("3.2").priority_override)

    def test_an_override_is_clamped_to_the_scale(self):
        p = plan()
        actions.override_priority(p, "3.2", 99, "top of the list", user="Jacob")
        self.assertEqual(p.review("3.2").priority_override, 5.0)

    def test_mandated_reviews_sort_above_everything(self):
        p = plan()
        ordered = sorted(p.reviews, key=lambda r: scoring.sort_key(r, p.weights))
        self.assertTrue(all(r.mandated for r in ordered[:3]))


class Staging(unittest.TestCase):
    def test_mandated_reviews_start_in_the_plan(self):
        p = plan()
        self.assertEqual({r.ref for r in staging.in_plan(p.reviews)}, {"4.1", "5.1", "7.2"})

    def test_descoping_requires_a_rationale(self):
        p = plan()
        actions.stage(p, "3.2", user="Jacob")
        with self.assertRaises(RationaleRequired):
            actions.descope(p, "3.2", "", user="Jacob")
        self.assertTrue(p.review("3.2").in_plan)

    def test_a_mandated_review_cannot_be_descoped_at_all(self):
        p = plan()
        with self.assertRaises(RationaleRequired):
            actions.descope(p, "4.1", "no capacity this year", user="Jacob")
        self.assertTrue(p.review("4.1").in_plan)

    def test_a_descoped_review_is_kept_not_deleted(self):
        p = plan()
        actions.stage(p, "3.2", user="Jacob")
        actions.descope(p, "3.2", "Covered by the group AI thematic.", user="Jacob")
        review = p.review("3.2")
        self.assertTrue(review.descoped)
        self.assertFalse(review.in_plan)
        self.assertIn(review, p.reviews)
        self.assertEqual(review.descope_rationale, "Covered by the group AI thematic.")

    def test_unstaged_without_a_reason_is_reported_as_outstanding_not_descoped(self):
        p = plan()
        outstanding = staging.outstanding_rationales(p.reviews)
        self.assertEqual(len(outstanding), 17)  # the 20 candidates less the 3 mandated
        self.assertEqual(staging.descoped(p.reviews), [])

    def test_restaging_clears_the_old_descope_reason(self):
        p = plan()
        actions.stage(p, "3.2", user="Jacob")
        actions.descope(p, "3.2", "Not this year.", user="Jacob")
        actions.stage(p, "3.2", user="Jacob")
        self.assertEqual(p.review("3.2").descope_rationale, "")
        self.assertFalse(p.review("3.2").descoped)

    def test_bulk_staging_takes_critical_and_high_only(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        for review in staging.in_plan(p.reviews):
            self.assertIn(scoring.band_of(review, p.weights),
                          (Band.MANDATED, Band.CRITICAL, Band.HIGH))

    def test_clearing_staging_keeps_the_mandated_floor(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        actions.clear_staging(p, user="Jacob")
        self.assertEqual({r.ref for r in staging.in_plan(p.reviews)}, {"4.1", "5.1", "7.2"})


class Capacity(unittest.TestCase):
    def test_fte_follows_the_effort_size(self):
        for size, fte in [(EffortSize.S, 2), (EffortSize.M, 3), (EffortSize.L, 4)]:
            self.assertEqual(Review(ref="x", title="t", assurance_function="f",
                                    effort_size=size).fte, fte)

    def test_a_per_review_override_beats_the_size_default(self):
        p = plan()
        actions.set_fte(p, "3.1", 7, user="Jacob")
        self.assertEqual(p.review("3.1").fte, 7)
        actions.set_fte(p, "3.1", None, user="Jacob")
        self.assertEqual(p.review("3.1").fte, 3)  # M

    def test_only_in_plan_reviews_draw_capacity(self):
        p = plan()
        before = capacity.bottom_up_fill(p.reviews, p.capacities)
        actions.stage(p, "3.1", user="Jacob")
        after = capacity.bottom_up_fill(p.reviews, p.capacities)
        self.assertEqual(after.additional_fte - before.additional_fte, 3)

    def test_mandated_demand_is_counted_separately_and_first(self):
        p = plan()
        fill = capacity.bottom_up_fill(p.reviews, p.capacities)
        self.assertEqual(fill.mandated_fte, 10)  # L(4) + L(4) + S(2)
        self.assertEqual(fill.additional_fte, 0)
        self.assertEqual(fill.remaining_after_mandated, fill.annual_fte_quarters - 10)

    def test_inactive_functions_contribute_no_capacity(self):
        p = plan()
        annual = capacity.bottom_up_fill(p.reviews, p.capacities).annual_fte_quarters
        self.assertEqual(annual, 54 * 4)  # only the six staffed functions

    def test_a_quarter_over_its_capacity_is_flagged(self):
        reviews = [
            Review(ref=f"x{i}", title="t", assurance_function="F", effort_size=EffortSize.L,
                   staged=True, planned_quarter=Quarter.Q1)
            for i in range(3)
        ]
        load = capacity.function_load(reviews, FunctionCapacity(name="F", fte_per_quarter=8))
        self.assertEqual(load.quarters[0].demand, 12)
        self.assertTrue(load.quarters[0].over)
        self.assertTrue(load.over)
        self.assertEqual(load.quarters[0].headroom, -4)


class Scheduling(unittest.TestCase):
    def test_the_waterfall_never_exceeds_a_quarter_of_capacity(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        actions.waterfall(p, user="Jacob")
        for cap in p.capacities:
            if not cap.is_active:
                continue
            for load in capacity.function_load(p.reviews, cap).quarters:
                self.assertLessEqual(load.demand, load.capacity, f"{cap.name} {load.quarter}")

    def test_it_packs_the_earliest_quarter_with_room(self):
        reviews = [
            Review(ref="a", title="t", assurance_function="F", effort_size=EffortSize.S,
                   staged=True, scores=Scores(5, 5, 5, 5)),
            Review(ref="b", title="t", assurance_function="F", effort_size=EffortSize.S,
                   staged=True, scores=Scores(1, 1, 1, 1)),
        ]
        caps = [FunctionCapacity(name="F", fte_per_quarter=2)]
        result = scheduling.waterfall(reviews, caps, Weights())
        self.assertEqual(result.quarters["a"], Quarter.Q1)   # higher priority goes first
        self.assertEqual(result.quarters["b"], Quarter.Q2)   # then the next quarter with room

    def test_a_mandated_review_keeps_the_quarter_its_go_live_implies(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        actions.waterfall(p, user="Jacob")
        self.assertEqual(p.review("4.1").planned_quarter, Quarter.Q1)  # go-live 18 Mar 2027
        self.assertEqual(p.review("7.2").planned_quarter, Quarter.Q3)  # go-live 1 Sep 2026

    def test_what_cannot_fit_is_left_unscheduled_and_reported(self):
        reviews = [
            Review(ref=f"x{i}", title="t", assurance_function="F", effort_size=EffortSize.L,
                   staged=True, scores=Scores(3, 3, 3, 3))
            for i in range(6)
        ]
        caps = [FunctionCapacity(name="F", fte_per_quarter=4)]
        result = scheduling.waterfall(reviews, caps, Weights())
        self.assertEqual(len(result.placed), 4)     # one L per quarter
        self.assertEqual(len(result.unplaced), 2)
        self.assertIn("could not fit", result.summary)

    def test_clearing_quarters_leaves_the_mandated_ones_alone(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        actions.waterfall(p, user="Jacob")
        actions.clear_quarters(p, user="Jacob")
        self.assertIsNotNone(p.review("4.1").planned_quarter)
        self.assertIsNone(p.review("3.4").planned_quarter)


class Approval(unittest.TestCase):
    def test_the_route_follows_the_review_type(self):
        p = plan()
        self.assertEqual(approval.route_of(p.review("4.1")), ApprovalRoute.IRR)     # mandated
        self.assertEqual(approval.route_of(p.review("3.1")), ApprovalRoute.RCA)     # RCA-linked
        self.assertEqual(approval.route_of(p.review("3.2")), ApprovalRoute.STANDARD)

    def test_each_route_has_exactly_one_gate(self):
        p = plan()
        self.assertEqual(approval.gate_of(p.review("4.1")), "IRR sign-off")
        self.assertEqual(approval.gate_of(p.review("3.1")), "RCA owner sign-off")
        self.assertEqual(approval.gate_of(p.review("3.2")), "1LOD / L2 sign-off")

    def test_returning_a_review_needs_a_comment(self):
        p = plan()
        with self.assertRaises(CommentRequired):
            actions.sign_off(p, "4.1", "Returned", "", user="Jacob")
        self.assertEqual(p.review("4.1").approval.status, ApprovalStatus.PENDING)

    def test_approving_records_who_and_when(self):
        p = plan()
        actions.sign_off(p, "4.1", "Approved", "IRR pack reviewed", user="Jacob")
        signed = p.review("4.1").approval
        self.assertEqual(signed.status, ApprovalStatus.APPROVED)
        self.assertEqual(signed.by, "Jacob")
        self.assertTrue(signed.at)

    def test_irr_reviews_sharing_an_obligation_are_linked(self):
        p = plan()
        a = p.review("4.1")
        twin = Review(ref="EXT-9", title="Same obligation, another team",
                      assurance_function="Financial Crime Assurance", mandated=True, staged=True,
                      rris_ids=list(a.rris_ids))
        p.reviews.append(twin)
        self.assertEqual([r.ref for r in approval.related_irr(a, p.reviews)], ["EXT-9"])

    def test_an_unrelated_irr_review_is_not_linked(self):
        p = plan()
        self.assertEqual(approval.related_irr(p.review("4.1"), p.reviews), [])


class AddingReviews(unittest.TestCase):
    def test_a_mandated_review_is_pinned_into_the_plan_on_arrival(self):
        p = plan()
        review = actions.add_review(p, {
            "mandated": True, "title": "New return",
            "assurance_function": "Treasury Risk Assurance",
            "rationale": "First live submissions.", "go_live": "18 Mar 2027",
        }, user="Jacob")
        self.assertTrue(review.in_plan)
        self.assertEqual(review.planned_quarter, Quarter.Q1)
        self.assertEqual(review.origin.value, "Regulatory Assurance")
        self.assertIsNone(review.scores)  # rule 5: not driver-scored

    def test_a_risk_led_review_queues_unstaged_and_is_scored(self):
        p = plan()
        review = actions.add_review(p, {
            "title": "Model change governance", "assurance_function": "Traded Risk Assurance",
            "rationale": "Repeat findings.", "scores": {"risk": 4, "urgency": 3,
                                                        "coverage_gap": 4, "change": 3},
        }, user="Jacob")
        self.assertFalse(review.staged)
        self.assertEqual(review.origin.value, "Risk Assurance")
        self.assertEqual(review.scores.risk, 4)

    def test_a_review_without_a_rationale_is_refused(self):
        p = plan()
        with self.assertRaises(PlanningError):
            actions.add_review(p, {"title": "x", "assurance_function": "Traded Risk Assurance"},
                               user="Jacob")

    def test_the_rationale_lands_on_both_helios_narrative_columns(self):
        p = plan()
        review = actions.add_review(p, {
            "title": "x", "assurance_function": "Traded Risk Assurance", "rationale": "Because.",
        }, user="Jacob")
        self.assertEqual(review.helios["reviewDetail"], "Because.")
        self.assertEqual(review.helios["scopeRationale"], "Because.")

    def test_refs_do_not_collide(self):
        p = plan()
        refs = {actions.add_review(p, {"title": f"r{i}", "rationale": "x",
                                       "assurance_function": "Traded Risk Assurance"},
                                   user="Jacob").ref for i in range(3)}
        self.assertEqual(len(refs), 3)

    def test_a_seeded_candidate_cannot_be_deleted_only_descoped(self):
        p = plan()
        with self.assertRaises(PlanningError):
            actions.remove_review(p, "3.1", user="Jacob")
        self.assertIsNotNone(p.review("3.1"))

    def test_an_added_review_can_be_deleted(self):
        p = plan()
        ref = actions.add_review(p, {"title": "x", "rationale": "y",
                                     "assurance_function": "Traded Risk Assurance"},
                                 user="Jacob").ref
        actions.remove_review(p, ref, user="Jacob")
        with self.assertRaises(NotFound):
            p.review(ref)


class AuditTrail(unittest.TestCase):
    def test_every_change_leaves_a_line_attributed_to_the_user(self):
        p = plan()
        actions.stage(p, "3.1", user="Jacob")
        actions.set_weights(p, {"risk": 2}, user="Jacob")
        actions.waterfall(p, user="Jacob")
        self.assertEqual(len(p.audit), 3)
        self.assertTrue(all(a.user == "Jacob" for a in p.audit))

    def test_an_unnamed_user_is_recorded_as_unattributed_rather_than_blank(self):
        p = plan()
        actions.stage(p, "3.1", user="")
        self.assertEqual(p.audit[0].user, "Unattributed")

    def test_the_newest_entry_is_first(self):
        p = plan()
        actions.stage(p, "3.1", user="Jacob")
        actions.stage(p, "3.2", user="Jacob")
        self.assertEqual(p.audit[0].ref, "3.2")

    def test_a_refused_change_leaves_no_audit_line(self):
        p = plan()
        with self.assertRaises(RationaleRequired):
            actions.override_priority(p, "3.2", 4.9, "", user="Jacob")
        self.assertEqual(p.audit, [])

    def test_the_override_line_carries_both_numbers_and_the_reason(self):
        p = plan()
        actions.override_priority(p, "3.2", 4.9, "Board asked", user="Jacob")
        self.assertIn("4.90", p.audit[0].detail)
        self.assertIn("computed 4.25", p.audit[0].detail)
        self.assertIn("Board asked", p.audit[0].detail)


class Versions(unittest.TestCase):
    def test_a_version_captures_the_plan_as_it_stands(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        version = p.save_version(user="Jacob", label="Pre-L2 cut")
        self.assertEqual(version.summary()["in_plan"], 10)

    def test_restoring_puts_the_shaped_plan_back(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        p.save_version(user="Jacob", label="Cut A")
        actions.clear_staging(p, user="Jacob")
        self.assertEqual(len(staging.in_plan(p.reviews)), 3)
        p.restore_version("1", user="Jacob")
        self.assertEqual(len(staging.in_plan(p.reviews)), 10)

    def test_restoring_does_not_rewind_the_audit_trail(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        p.save_version(user="Jacob", label="Cut A")
        before = len(p.audit)
        p.restore_version("1", user="Jacob")
        self.assertGreater(len(p.audit), before)
        self.assertEqual(p.audit[0].action, "Version restored")

    def test_restoring_a_version_that_does_not_exist_is_refused(self):
        with self.assertRaises(NotFound):
            plan().restore_version("99", user="Jacob")


class PlanFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "plan.json"
        self.store = Store(self.path)

    def test_a_missing_file_starts_from_the_seeded_candidate_list(self):
        self.assertEqual(len(self.store.load().reviews), 20)
        self.assertFalse(self.path.exists())

    def test_everything_survives_a_save_and_reload(self):
        with self.store.mutate() as p:
            actions.stage_critical_and_high(p, user="Jacob")
            actions.waterfall(p, user="Jacob")
            actions.override_priority(p, "3.2", 4.9, "Board asked", user="Jacob")
            actions.sign_off(p, "4.1", "Approved", "IRR pack reviewed", user="Jacob")
            p.save_version(user="Jacob", label="Cut A")

        back = self.store.load()
        self.assertEqual(len(staging.in_plan(back.reviews)), 10)
        self.assertEqual(back.review("3.2").priority_override, 4.9)
        self.assertEqual(back.review("4.1").approval.status, ApprovalStatus.APPROVED)
        self.assertEqual(back.review("4.1").planned_quarter, Quarter.Q1)
        self.assertEqual(len(back.versions), 1)
        self.assertEqual(len(back.audit), 5)

    def test_the_file_is_utf8_json_a_human_can_read(self):
        with self.store.mutate() as p:
            actions.stage(p, "5.1", user="Jacob")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["year"], "2027")
        # Not —-escaped: the file is meant to be diffable in a review.
        self.assertIn("—", self.path.read_text(encoding="utf-8"))

    def test_a_failed_save_leaves_the_previous_plan_intact(self):
        with self.store.mutate() as p:
            actions.stage(p, "5.2", user="Jacob")
        good = self.path.read_bytes()

        class Unserialisable:
            pass

        broken = self.store.load()
        broken.reference["business"] = [Unserialisable()]
        with self.assertRaises(TypeError):
            self.store.save(broken)
        self.assertEqual(self.path.read_bytes(), good)
        self.assertEqual([p for p in self.path.parent.iterdir() if p.suffix == ".tmp"], [])

    def test_a_corrupt_plan_file_is_reported_not_silently_reseeded(self):
        self.path.write_text("{not json", encoding="utf-8")
        from helios.planning.errors import PlanFileError
        with self.assertRaises(PlanFileError):
            self.store.load()

    def test_reset_returns_to_the_seeded_plan(self):
        with self.store.mutate() as p:
            actions.stage_critical_and_high(p, user="Jacob")
        self.store.reset()
        self.assertEqual(len(staging.in_plan(self.store.load().reviews)), 3)


class Prestaging(unittest.TestCase):
    def test_planning_seeds_the_helios_row(self):
        p = plan()
        record = prestaging.read(p.review("4.1"))
        values = record["values"]
        self.assertEqual(values["reviewId"], "AREV-41")
        self.assertEqual(values["reviewType"], "Core - Externally mandated")
        self.assertEqual(values["assuranceFunction"], "Regulatory Reporting Assurance")
        self.assertEqual(values["targetStart"], "2027-03-18")
        self.assertEqual(values["planQuarter"], "Q1")

    def test_hand_entered_values_survive_and_derived_ones_are_recomputed(self):
        p = plan()
        actions.update_prestaging(p, "4.1", {
            "reviewCategory": "Global", "reviewLead": "45012345", "reviewTeam": "UK (RC)",
            "scopeRationale": "Scope.", "planQuarter": "Q4",
        }, user="Jacob")
        values = prestaging.read(p.review("4.1"))["values"]
        self.assertEqual(values["reviewLead"], "45012345")
        self.assertEqual(values["planQuarter"], "Q1")  # derived, not the supplied Q4

    def test_locations_follow_risk_radar_rather_than_being_typed_here(self):
        p = plan()
        actions.set_locations(p, "4.1", ["uk", "HK"], user="Jacob")
        self.assertEqual(prestaging.read(p.review("4.1"))["values"]["location"], "UK; Hong Kong")

    def test_a_review_becomes_helios_ready_once_the_gaps_are_filled(self):
        p = plan()
        self.assertFalse(prestaging.read(p.review("4.1"))["complete"])
        actions.update_prestaging(p, "4.1", {
            "reviewCategory": "Global", "reviewLead": "45012345",
            "reviewTeam": "UK (RC)", "scopeRationale": "Scope and rationale.",
        }, user="Jacob")
        self.assertTrue(prestaging.read(p.review("4.1"))["complete"])


class GovernanceExports(unittest.TestCase):
    def setUp(self):
        self.plan = plan()
        actions.stage_critical_and_high(self.plan, user="Jacob")
        actions.waterfall(self.plan, user="Jacob")

    def rows(self, text: str) -> list[list[str]]:
        return list(csv.reader(io.StringIO(text)))

    def test_the_shaped_plan_covers_the_in_plan_population_only(self):
        rows = self.rows(exports.plan_csv(self.plan))
        self.assertEqual(rows[0], exports.PLAN_HEADER)
        self.assertEqual(len(rows) - 1, 10)

    def test_mandated_reviews_carry_no_driver_scores_in_the_export(self):
        rows = self.rows(exports.plan_csv(self.plan))
        header, body = rows[0], rows[1:]
        row = next(r for r in body if r[header.index("Mandated")] == "Yes")
        self.assertEqual(row[header.index("Risk score")], "")
        self.assertEqual(row[header.index("Effective priority")], "")

    def test_the_approval_view_names_the_gate_and_the_decision(self):
        actions.sign_off(self.plan, "4.1", "Approved", "IRR pack reviewed", user="Jacob")
        rows = self.rows(exports.approval_csv(self.plan))
        header = rows[0]
        row = next(r for r in rows[1:] if r[0] == "4.1")
        self.assertEqual(row[header.index("Gate")], "IRR sign-off")
        self.assertEqual(row[header.index("Status")], "Approved")
        self.assertEqual(row[header.index("Signed off by")], "Jacob")

    def test_the_audit_export_reads_oldest_first(self):
        rows = self.rows(exports.audit_csv(self.plan))
        self.assertEqual(rows[0], exports.AUDIT_HEADER)
        self.assertEqual(rows[1][3], "Bulk staged")  # the first thing that happened

    def test_the_helios_export_covers_the_in_plan_population(self):
        rows = exports.helios_rows(self.plan)
        self.assertEqual(len(rows), 10)

    def test_every_governance_export_is_uniformly_quoted_and_crlf(self):
        for text in (exports.plan_csv(self.plan), exports.approval_csv(self.plan),
                     exports.audit_csv(self.plan)):
            self.assertTrue(text.startswith('"'))
            self.assertTrue(text.endswith("\r\n"))


class PlanView(unittest.TestCase):
    def test_the_funnel_adds_up(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")  # 3.2 is Critical, so already in
        self.assertEqual(views.stats(p)["in_plan"], 10)

        actions.descope(p, "3.2", "Covered elsewhere.", user="Jacob")
        s = views.stats(p)
        self.assertEqual(s["candidates"], 20)
        self.assertEqual(s["in_plan"], 9)
        self.assertEqual(s["descoped"], 1)

    def test_the_shaped_view_groups_by_taxonomy_and_totals_fte(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        groups = views.shaped_plan(p)
        self.assertEqual(sum(g["fte"] for g in groups),
                         sum(r.fte for r in staging.in_plan(p.reviews)))

    def test_a_renamed_taxonomy_label_does_not_orphan_a_review(self):
        p = plan()
        actions.set_reference(p, "taxonomy",
                              [{"code": "change-ai", "label": "AI & model change"}], user="Jacob")
        self.assertEqual(views.taxonomy_label(p, "change-ai"), "AI & model change")
        self.assertEqual(views.taxonomy_label(p, "op-res"), "op-res")  # falls back to the code

    def test_the_whole_payload_is_json_serialisable(self):
        p = plan()
        actions.stage_critical_and_high(p, user="Jacob")
        json.dumps(views.whole(p))


class SeedData(unittest.TestCase):
    def test_the_candidate_list_matches_the_prototype(self):
        reviews = seed.reviews()
        self.assertEqual(len(reviews), 20)
        self.assertEqual(len([r for r in reviews if r.mandated]), 3)
        self.assertEqual(len([r for r in reviews if r.rca_linked]), 7)

    def test_mandated_reviews_carry_their_obligation(self):
        by_ref = {r.ref: r for r in seed.reviews()}
        self.assertEqual(by_ref["4.1"].go_live, date(2027, 3, 18))
        self.assertEqual(by_ref["4.1"].rris_ids, ["RRIS-10421"])
        self.assertTrue(by_ref["5.1"].regulation.startswith("PS1/26"))

    def test_every_review_names_a_function_that_exists(self):
        names = {c.name for c in seed.capacities()}
        for review in seed.reviews():
            self.assertIn(review.assurance_function, names)


if __name__ == "__main__":
    unittest.main()

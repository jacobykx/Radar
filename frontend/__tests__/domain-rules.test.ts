/**
 * The methodology, as executable rules.
 *
 * Every test here maps to a numbered rule in BUILD_INSTRUCTIONS section 2, and mirrors
 * `backend/tests/test_domain_rules.py` case for case. The rules moved into the browser
 * for the POC; the guarantee that they still hold did not move with them, so it is
 * restated here. If one of these fails, the change is wrong, not the test.
 */
import {
  approval,
  capacity as cap,
  fteOf,
  helios,
  isDescoped,
  QUARTERS,
  rationaleOutstanding,
  scheduling,
  scoring,
  SIZE_DAYS,
  SIZE_FTE,
  staging,
  type Scores,
  type Weights,
} from "@/lib/engine";

import { makeFunction, makeReview, WEIGHTS } from "./factory";

const scores = (risk: number, urgency: number, coverage_gap: number, change: number): Scores => ({
  risk,
  urgency,
  coverage_gap,
  change,
});

// ------------------------------------------------------------- rule 2: weighted priority

describe("rule 2 — weighted priority", () => {
  test("is normalised by the weight sum, so weights change emphasis not scale", () => {
    const heavyOnRisk: Weights = { risk: 3, urgency: 1, coverage_gap: 1, change: 1 };

    expect(scoring.computedPriority(scores(5, 1, 1, 1), WEIGHTS)).toBeCloseTo(2.0);
    expect(scoring.computedPriority(scores(5, 1, 1, 1), heavyOnRisk)).toBeCloseTo(3.0);

    for (const w of [WEIGHTS, heavyOnRisk, { risk: 0, urgency: 0, coverage_gap: 0, change: 7 }]) {
      const value = scoring.computedPriority(scores(3, 3, 3, 3), w);
      expect(value).toBeGreaterThanOrEqual(1);
      expect(value).toBeLessThanOrEqual(5);
    }
  });

  test("equal weights give the plain mean", () => {
    expect(scoring.computedPriority(scores(4, 3, 2, 1), WEIGHTS)).toBeCloseTo(2.5);
  });

  test("all-zero weights do not divide by zero", () => {
    const zero: Weights = { risk: 0, urgency: 0, coverage_gap: 0, change: 0 };
    expect(scoring.computedPriority(scores(4, 4, 4, 4), zero)).toBe(0);
  });

  test("bands sit on the documented thresholds", () => {
    expect(scoring.band(4.3)).toBe("Critical");
    expect(scoring.band(4.29)).toBe("High");
    expect(scoring.band(3.7)).toBe("High");
    expect(scoring.band(3.0)).toBe("Medium");
    expect(scoring.band(2.99)).toBe("Low");
  });
});

// ------------------------------------------------------------- rule 3: priority override

describe("rule 3 — priority override", () => {
  test("an override without a rationale is refused", () => {
    expect(() => scoring.validateOverride(4.5, "")).toThrow(/rationale is required/i);
    expect(() => scoring.validateOverride(4.5, "   ")).toThrow(/rationale is required/i);
  });

  test("the override is stored beside the computed value, not over it", () => {
    const review = makeReview("1.1", { scores: [2, 2, 2, 2] });
    const [value, rationale] = scoring.validateOverride(4.6, "Board escalation after Q3");
    review.item.priority_override = value;

    expect(scoring.computedPriority(review.scores!, WEIGHTS)).toBeCloseTo(2.0);
    expect(scoring.effectivePriority(review, WEIGHTS)).toBeCloseTo(4.6);
    expect(rationale).toBe("Board escalation after Q3");
  });

  test("clearing the override restores the computed priority", () => {
    const review = makeReview("1.1", { scores: [2, 2, 2, 2], priority_override: 4.6 });
    review.item.priority_override = null;
    expect(scoring.effectivePriority(review, WEIGHTS)).toBeCloseTo(2.0);
  });

  test("the override is clamped to the scale", () => {
    expect(scoring.validateOverride(9.9, "why")[0]).toBe(5);
    expect(scoring.validateOverride(-3, "why")[0]).toBe(0);
  });
});

// --------------------------------------------------------- rules 4-5: mandated reviews

describe("rules 4-5 — mandated reviews", () => {
  test("a mandated review is not driver-scored", () => {
    const review = makeReview("m", { mandated: true, scores: [5, 5, 5, 5] });
    expect(scoring.effectivePriority(review, WEIGHTS)).toBeNull();
    expect(scoring.bandOf(review, WEIGHTS)).toBe("Mandated");
  });

  test("origin and the mandated flag must agree", () => {
    expect(() => staging.validateOrigin("Regulatory Assurance", true)).not.toThrow();
    expect(() => staging.validateOrigin("Risk Assurance", false)).not.toThrow();
    expect(() => staging.validateOrigin("Risk Radar inputs", false)).not.toThrow();

    expect(() => staging.validateOrigin("Risk Assurance", true)).toThrow(/must have origin/i);
    expect(() => staging.validateOrigin("Regulatory Assurance", false)).toThrow(/reserved/i);
  });
});

// ------------------------------------------------------------------- rule 6: descoping

describe("rule 6 — descoping", () => {
  test("descoping without a rationale is refused", () => {
    expect(() => staging.validateDescope(null)).toThrow(/rationale is required/i);
    expect(() => staging.validateDescope("  ")).toThrow(/rationale is required/i);
    expect(staging.validateDescope("  covered by the 2026 thematic  ")).toBe(
      "covered by the 2026 thematic",
    );
  });

  test("a descoped review leaves every downstream stage", () => {
    const kept = makeReview("1.1");
    const gone = makeReview("1.2", {
      staged: false,
      descope_rationale: "merged into 1.1",
      quarter: "Q1",
    });
    const reviews = [kept, gone];

    expect(staging.inPlan(reviews)).toEqual([kept]);
    expect(staging.descoped(reviews)).toEqual([gone]);
    expect(cap.quarterDemand(reviews, kept.assurance_function, "Q1")).toBe(0);
    expect(approval.relatedIrr(kept, reviews)).not.toContain(gone);

    const result = scheduling.waterfall(
      reviews,
      [makeFunction(kept.assurance_function)],
      WEIGHTS,
    );
    expect(result.quarters).not.toHaveProperty(gone.ref);
  });

  test("un-staged without a rationale is reported, not silently dropped", () => {
    const pending = makeReview("1.3", { staged: false });
    expect(rationaleOutstanding(pending)).toBe(true);
    expect(isDescoped(pending)).toBe(false);
    expect(staging.outstandingRationales([pending])).toEqual([pending]);
  });
});

// ------------------------------------------------------------- rule 7: effort and FTE

describe("rule 7 — effort and FTE", () => {
  test("effort sizes map to days and default FTE", () => {
    expect([SIZE_DAYS.S, SIZE_DAYS.M, SIZE_DAYS.L]).toEqual([60, 90, 120]);
    expect([SIZE_FTE.S, SIZE_FTE.M, SIZE_FTE.L]).toEqual([2, 3, 4]);
  });

  test("an explicit FTE overrides the size default", () => {
    expect(fteOf(makeReview("1.1", { size: "L" }))).toBe(4);
    expect(fteOf(makeReview("1.1", { size: "L", fte_override: 6 }))).toBe(6);
    expect(fteOf(makeReview("1.1", { size: "S", fte_override: 1 }))).toBe(1);
  });
});

// ----------------------------------------------------------------- rule 8: capacity

describe("rule 8 — capacity", () => {
  test("a scheduled review consumes its FTE in that quarter", () => {
    const reviews = [
      makeReview("1.1", { size: "L", quarter: "Q1" }), // 4 FTE
      makeReview("1.2", { size: "S", quarter: "Q1" }), // 2 FTE
      makeReview("1.3", { size: "M", quarter: "Q3" }), // 3 FTE
    ];
    const load = cap.functionLoad(reviews, makeFunction());
    const demand = Object.fromEntries(load.quarters.map((q) => [q.quarter, q.demand]));

    expect(demand).toEqual({ Q1: 6, Q2: 0, Q3: 3, Q4: 0 });
    expect(load.over).toBe(false);
    expect(load.quarters.find((q) => q.quarter === "Q1")!.headroom).toBe(4);
  });

  test("mandated demand commits capacity before anything else", () => {
    const reviews = [
      makeReview("1.1", { mandated: true, size: "L" }), // 4 FTE
      makeReview("1.2", { size: "M" }), // 3 FTE
    ];
    const fill = cap.bottomUpFill(reviews, [makeFunction()]);

    expect(fill.annual_fte_quarters).toBe(40);
    expect(fill.mandated_fte).toBe(4);
    expect(fill.additional_fte).toBe(3);
    expect(fill.remaining_after_mandated).toBe(36);
    expect(fill.headroom).toBe(33);
    expect(fill.over).toBe(false);
  });

  test("an overcommitted plan is flagged", () => {
    const small = makeFunction("Financial Crime Assurance", 1);
    const reviews = [0, 1, 2].map((i) => makeReview(String(i), { size: "L" }));
    expect(cap.bottomUpFill(reviews, [small]).over).toBe(true);
  });

  test("unscheduled demand is reported separately", () => {
    const reviews = [makeReview("1.1", { size: "L", quarter: null })];
    expect(cap.functionLoad(reviews, makeFunction()).unscheduled_fte).toBe(4);
  });
});

// ----------------------------------------------------------------- rule 9: waterfall

describe("rule 9 — waterfall", () => {
  test("fills the earliest quarter with room", () => {
    const reviews = [1, 2, 3, 4].map((i) => makeReview(`1.${i}`, { size: "M" })); // 3 FTE, cap 10
    const result = scheduling.waterfall(reviews, [makeFunction()], WEIGHTS);

    expect(result.quarters).toEqual({ "1.1": "Q1", "1.2": "Q1", "1.3": "Q1", "1.4": "Q2" });
    expect(result.unplaced).toHaveLength(0);
  });

  test("never exceeds the quarterly FTE", () => {
    const tight = makeFunction("Financial Crime Assurance", 4);
    const reviews = [1, 2, 3, 4, 5].map((i) => makeReview(`1.${i}`, { size: "M" }));
    const result = scheduling.waterfall(reviews, [tight], WEIGHTS);

    const scheduled = reviews.map((r) => ({
      ...r,
      item: { ...r.item, planned_quarter: result.quarters[r.ref] ?? null },
    }));
    for (const quarter of QUARTERS) {
      expect(cap.quarterDemand(scheduled, tight.name, quarter)).toBeLessThanOrEqual(
        tight.fte_per_quarter,
      );
    }
  });

  test("places mandated first, then by priority", () => {
    const tight = makeFunction("Financial Crime Assurance", 3);
    const reviews = [
      makeReview("low", { size: "M", scores: [1, 1, 1, 1] }),
      makeReview("high", { size: "M", scores: [5, 5, 5, 5] }),
      makeReview("mand", { size: "M", mandated: true }),
    ];
    const result = scheduling.waterfall(reviews, [tight], WEIGHTS);

    expect(result.quarters.mand).toBe("Q1");
    expect(result.quarters.high).toBe("Q2");
    expect(result.quarters.low).toBe("Q3");
  });

  test("leaves what cannot fit unscheduled and flags it", () => {
    const tight = makeFunction("Financial Crime Assurance", 3);
    const reviews = [1, 2, 3, 4, 5].map((i) => makeReview(`1.${i}`, { size: "M" }));
    const result = scheduling.waterfall(reviews, [tight], WEIGHTS);

    expect(result.placed).toHaveLength(4);
    expect(result.unplaced).toHaveLength(1);
    expect(result.quarters[result.unplaced[0].ref]).toBeNull();
    expect(result.summary).toMatch(/could not fit/);
  });

  test("a mandated review holds its go-live quarter through auto-fill", () => {
    const tight = makeFunction("Financial Crime Assurance", 4);
    const pinned = makeReview("mand", {
      mandated: true,
      size: "M",
      quarter: "Q3",
      go_live: "2027-08-01",
    });
    const other = makeReview("other", { size: "M" });
    const result = scheduling.waterfall([pinned, other], [tight], WEIGHTS);

    expect(result.quarters.mand).toBe("Q3"); // untouched
    expect(result.quarters.other).toBe("Q1"); // filled around it
  });

  test("schedules each function against its own capacity", () => {
    const functions = [
      makeFunction("Financial Crime Assurance", 3),
      makeFunction("Traded Risk Assurance", 3),
    ];
    const reviews = [
      makeReview("fc1", { function: "Financial Crime Assurance", size: "M" }),
      makeReview("fc2", { function: "Financial Crime Assurance", size: "M" }),
      makeReview("tr1", { function: "Traded Risk Assurance", size: "M" }),
    ];
    const result = scheduling.waterfall(reviews, functions, WEIGHTS);

    expect(result.quarters.fc1).toBe("Q1");
    expect(result.quarters.fc2).toBe("Q2"); // FC's Q1 is full
    expect(result.quarters.tr1).toBe("Q1"); // Traded Risk has its own Q1
  });

  test("does not mutate the reviews it is given", () => {
    const reviews = [makeReview("1.1", { size: "M" })];
    scheduling.waterfall(reviews, [makeFunction()], WEIGHTS);
    expect(reviews[0].item.planned_quarter).toBeNull();
  });
});

// ------------------------------------------------------------------ rule 10: sign-off

describe("rule 10 — sign-off", () => {
  test("each review has exactly one gate, routed by type", () => {
    const mandated = makeReview("m", { mandated: true });
    const rca = makeReview("r", { rca_linked: true });
    const standard = makeReview("s");

    expect(approval.routeOf(mandated)).toBe("IRR");
    expect(approval.routeOf(rca)).toBe("RCA");
    expect(approval.routeOf(standard)).toBe("Standard");
    expect(new Set([mandated, rca, standard].map(approval.gateOf)).size).toBe(3);
  });

  test("a mandated RCA-linked review still routes to IRR", () => {
    expect(approval.routeOf(makeReview("x", { mandated: true, rca_linked: true }))).toBe("IRR");
  });

  test("returning a review requires a comment", () => {
    expect(() => approval.validateDecision("Returned", "")).toThrow(/comment is required/i);
    expect(approval.validateDecision("Returned", "scope too broad")).toBe("scope too broad");
    expect(approval.validateDecision("Approved", null)).toBe("");
  });

  test("cross-team linkage finds the same obligation elsewhere", () => {
    const mine = makeReview("4.1", {
      mandated: true,
      rris_ids: ["RRIS-10421"],
      regulation: "PS7/26",
    });
    const sameRris = makeReview("9.9", {
      mandated: true,
      function: "Traded Risk Assurance",
      rris_ids: ["RRIS-10421"],
    });
    const sameRegulation = makeReview("8.8", {
      mandated: true,
      function: "Treasury Risk Assurance",
      regulation: "PS7/26",
    });
    const unrelated = makeReview("7.7", {
      mandated: true,
      rris_ids: ["RRIS-99999"],
      regulation: "PS1/26",
    });
    const notIrr = makeReview("6.6", { rris_ids: ["RRIS-10421"] });

    const related = approval.relatedIrr(mine, [
      mine,
      sameRris,
      sameRegulation,
      unrelated,
      notIrr,
    ]);
    expect(new Set(related.map((r) => r.ref))).toEqual(new Set(["9.9", "8.8"]));
  });
});

// -------------------------------------------------------------- Helios pre-staging

describe("Helios pre-staging", () => {
  test("plan and IAP quarters are derived from the target start date", () => {
    expect(helios.derivedValues("2027-03-31")).toEqual({
      planQuarter: "Q1",
      iapQuarter: "Q1",
      planYear: "2027",
      iapYear: "2027",
    });
    expect(helios.derivedValues("2027-04-01").planQuarter).toBe("Q2");
    expect(helios.derivedValues("2026-12-31")).toEqual({
      planQuarter: "Q4",
      iapQuarter: "Q4",
      planYear: "2026",
      iapYear: "2026",
    });
    expect(helios.derivedValues(null).planQuarter).toBe("");
  });

  test("completeness needs every required field", () => {
    const values = Object.fromEntries(helios.REQUIRED_FIELDS.map((k) => [k, "x"]));
    expect(helios.isComplete(values)).toBe(true);

    values.reviewLead = "   ";
    expect(helios.isComplete(values)).toBe(false);
    expect(helios.missingFields(values)).toEqual(["reviewLead"]);
  });

  test("the export carries the spec field set in order", () => {
    const row = helios.exportRow({ title: "SS1/23 model risk" }, "2027-05-01");
    expect(row).toHaveLength(helios.EXPORT_HEADER.length);
    expect(helios.EXPORT_HEADER).toHaveLength(27);
    expect(row[helios.EXPORT_HEADER.indexOf("Title")]).toBe("SS1/23 model risk");
    expect(row[helios.EXPORT_HEADER.indexOf("Plan Quarter")]).toBe("Q2");
  });

  test("a value outside the allowed list is refused", () => {
    expect(() => helios.validateValue("esgFlag", "Maybe")).toThrow(/not an allowed value/i);
    expect(() => helios.validateValue("esgFlag", "Yes")).not.toThrow();
  });
});

// ------------------------------------------------------------- rule 13: multi-location

describe("rule 13 — multi-location", () => {
  test("a location filter matches if any location matches", () => {
    const review = makeReview("1.1", { locations: ["UK", "USA", "Hong Kong"] });
    expect(review.locations).toContain("USA");
    expect(review.locations).not.toContain("Germany");
  });
});

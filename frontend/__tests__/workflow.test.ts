/**
 * The workflow commands.
 *
 * These are the rules the FastAPI service enforced in `app/services` -- refusals,
 * audit entries, the descope cascade and version restore. In the POC they run in the
 * browser, so this is where "the API would have returned a 400" is now proved.
 */
import { select, workflow, type InstanceDoc } from "@/lib/engine";

import { makeFunction, makeInstance, makeReview } from "./factory";

const refs = (doc: InstanceDoc) => doc.reviews.map((r) => r.ref);

describe("staging and descoping", () => {
  test("descoping without a rationale is refused and changes nothing", () => {
    const doc = makeInstance([makeReview("1.1")]);
    expect(() => workflow.setStaged(doc, { ref: "1.1", staged: false })).toThrow(
      /rationale is required/i,
    );
    expect(doc.reviews[0].item.staged).toBe(true);
    expect(doc.audit).toHaveLength(0);
  });

  test("descoping with a rationale drops the review out of the plan and logs it", () => {
    const before = makeInstance([makeReview("1.1", { quarter: "Q1" })]);
    const { doc } = workflow.setStaged(before, {
      ref: "1.1",
      staged: false,
      rationale: "covered by the 2026 thematic",
    });

    const review = select.findReview(doc, "1.1")!;
    expect(review.item.staged).toBe(false);
    expect(review.item.planned_quarter).toBeNull();
    expect(select.planSummary(doc).descoped).toBe(1);
    expect(doc.audit[0]).toMatchObject({ action: "Descoped", review_ref: "1.1" });
    // the caller's document is untouched -- commands return a new one
    expect(before.reviews[0].item.staged).toBe(true);
  });

  test("bringing a review back into scope clears the rationale", () => {
    const start = makeInstance([
      makeReview("1.1", { staged: false, descope_rationale: "was descoped" }),
    ]);
    const { doc } = workflow.setStaged(start, { ref: "1.1", staged: true });

    expect(doc.reviews[0].item.descope_rationale).toBeNull();
    expect(select.planSummary(doc).in_scope).toBe(1);
  });

  test("a write against a stale row version is refused", () => {
    const doc = makeInstance([makeReview("1.1")]);
    expect(() =>
      workflow.setStaged(doc, {
        ref: "1.1",
        staged: false,
        rationale: "x",
        row_version: 99,
      }),
    ).toThrow(/changed since you loaded it/i);
  });
});

describe("priority override", () => {
  test("an override without a rationale is refused", () => {
    const doc = makeInstance([makeReview("1.1", { scores: [2, 2, 2, 2] })]);
    expect(() =>
      workflow.setPriorityOverride(doc, { ref: "1.1", value: 4.5, rationale: " " }),
    ).toThrow(/rationale is required/i);
  });

  test("the computed value survives the override and comes back when it is cleared", () => {
    const start = makeInstance([makeReview("1.1", { scores: [2, 2, 2, 2] })]);
    const { doc } = workflow.setPriorityOverride(start, {
      ref: "1.1",
      value: 4.6,
      rationale: "Board escalation",
    });

    const overridden = select.reviews(doc)[0];
    expect(overridden.computed_priority).toBeCloseTo(2.0);
    expect(overridden.effective_priority).toBeCloseTo(4.6);
    expect(overridden.priority_override_rationale).toBe("Board escalation");

    const cleared = select.reviews(workflow.clearPriorityOverride(doc, { ref: "1.1" }).doc)[0];
    expect(cleared.priority_override).toBeNull();
    expect(cleared.effective_priority).toBeCloseTo(2.0);
  });
});

describe("auto-fill", () => {
  test("persists the waterfall and reports what would not fit", () => {
    const tight = makeFunction("Financial Crime Assurance", 3);
    const start = makeInstance(
      [1, 2, 3, 4, 5].map((i) => makeReview(`1.${i}`, { size: "M" })),
      { functions: [tight] },
    );
    const { doc, result } = workflow.autofill(start);

    expect(result.placed).toHaveLength(4);
    expect(result.unplaced).toHaveLength(1);
    expect(select.planSummary(doc).unscheduled).toBe(1);
    expect(doc.audit[0].action).toBe("Quarters auto-filled");
  });

  test("clearing quarters unschedules everything", () => {
    const start = makeInstance([makeReview("1.1", { quarter: "Q2" })]);
    const { doc, result } = workflow.clearQuarters(start);

    expect(result).toBe(1);
    expect(doc.reviews[0].item.planned_quarter).toBeNull();
  });
});

describe("sign-off", () => {
  test("returning without a comment is refused; approving needs none", () => {
    const doc = makeInstance([makeReview("1.1")]);
    expect(() => workflow.decide(doc, { ref: "1.1", decision: "Returned" })).toThrow(
      /comment is required/i,
    );

    const approved = workflow.decide(doc, { ref: "1.1", decision: "Approved" }).doc;
    expect(select.reviews(approved)[0].approval_status).toBe("Approved");
    expect(approved.reviews[0].approval!.gate).toBe("1LOD / L2 sign-off");
  });

  test("bulk approve covers exactly the filtered view", () => {
    const start = makeInstance([
      makeReview("1.1", { function: "Financial Crime Assurance" }),
      makeReview("2.1", { function: "Traded Risk Assurance" }),
    ]);
    const { doc, result } = workflow.bulkApprove(start, { team: "Traded Risk Assurance" });

    expect(result).toEqual(["2.1"]);
    expect(select.reviews(doc).map((r) => r.approval_status)).toEqual(["Pending", "Approved"]);
  });

  test("a descoped review is not in the approval population at all", () => {
    const doc = makeInstance([
      makeReview("1.1"),
      makeReview("1.2", { staged: false, descope_rationale: "merged" }),
    ]);
    expect(select.approvalScope(doc).map((r) => r.ref)).toEqual(["1.1"]);
  });
});

describe("pre-staging", () => {
  test("derived fields are ignored when sent, and the quarter follows the start date", () => {
    const start = makeInstance([makeReview("1.1")]);
    const { doc } = workflow.updatePrestaging(start, {
      ref: "1.1",
      changes: { targetStart: "2027-05-01", planQuarter: "Q4" },
    });

    const values = select.prestagingValues(doc.reviews[0]);
    expect(values.planQuarter).toBe("Q2");
    expect(doc.reviews[0].prestaging.values.planQuarter).toBeUndefined();
  });

  test("a value outside the allowed list is refused", () => {
    const doc = makeInstance([makeReview("1.1")]);
    expect(() =>
      workflow.updatePrestaging(doc, { ref: "1.1", changes: { esgFlag: "Maybe" } }),
    ).toThrow(/not an allowed value/i);
  });

  test("only in-plan reviews are pre-staged", () => {
    const doc = makeInstance([
      makeReview("1.1"),
      makeReview("1.2", { staged: false, descope_rationale: "merged" }),
    ]);
    expect(select.prestagingRows(doc).map((r) => r.ref)).toEqual(["1.1"]);
  });
});

describe("adding a review", () => {
  test("both add-forms require a rationale, and origin must agree with mandated", () => {
    const doc = makeInstance([makeReview("1.1")]);

    expect(() =>
      workflow.addReview(doc, {
        title: "New review",
        origin: "Risk Assurance",
        assurance_function: "Financial Crime Assurance",
      }),
    ).toThrow(/rationale is required/i);

    const { doc: added, result } = workflow.addReview(doc, {
      title: "Regulatory review",
      origin: "Regulatory Assurance",
      assurance_function: "Financial Crime Assurance",
      rationale: "PS7/26 obligation",
      go_live: "2027-08-01",
    });

    expect(result).toBe("EXT-1");
    const review = select.findReview(added, "EXT-1")!;
    // Regulatory Assurance means mandated, which means pinned into its go-live quarter.
    expect(review.mandated).toBe(true);
    expect(review.item.staged).toBe(true);
    expect(review.item.planned_quarter).toBe("Q3");
    expect(refs(added)).toContain("EXT-1");
  });
});

describe("a newly added review flows through every stage", () => {
  test("a risk-led review reaches staging, capacity, the plan, sign-off and pre-staging", () => {
    const start = makeInstance([makeReview("1.1")]);
    const { doc: added, result: ref } = workflow.addReview(start, {
      title: "Thematic review of model change governance",
      origin: "Risk Assurance",
      assurance_function: "Financial Crime Assurance",
      taxonomy_code: "fincrime",
      business: "CIB",
      locations: ["UK", "Global"],
      effort_size: "L",
      rationale: "Repeat findings in the last two model change audits",
    });

    // Risk Radar: present, in the backlog, driver-scored at the neutral mid-point.
    const radar = select.reviews(added).find((r) => r.ref === ref)!;
    expect(radar.staged).toBe(false);
    expect(radar.origin).toBe("Risk Assurance");
    expect(radar.effective_priority).toBeCloseTo(3.0);
    expect(radar.fte).toBe(4); // L
    // Locations come back ordered by the reference list, not the order typed.
    expect(radar.locations).toEqual(["Global", "UK"]);

    // Out of the plan until staged, so no downstream stage sees it yet.
    expect(select.prestagingRows(added).map((r) => r.ref)).not.toContain(ref);
    expect(select.approvalScope(added).map((r) => r.ref)).not.toContain(ref);

    const staged = workflow.setStaged(added, { ref, staged: true }).doc;
    const { doc: filled } = workflow.autofill(staged);
    const quarter = select.findReview(filled, ref)!.item.planned_quarter;
    expect(quarter).not.toBeNull();

    // Staging & capacity: its FTE is drawn in the quarter it landed in.
    const load = select
      .capacityReport(filled)
      .functions.find((f) => f.function === "Financial Crime Assurance")!;
    expect(load.quarters.find((q) => q.quarter === quarter)!.demand).toBeGreaterThanOrEqual(4);

    // Shaped plan.
    const group = select
      .shapedPlan(filled)
      .groups.find((g) => g.function === "Financial Crime Assurance")!;
    expect(group.reviews.map((r) => r.ref)).toContain(ref);

    // Approval: in scope, on the Standard route, and it signs off.
    expect(select.approvalScope(filled).map((r) => r.ref)).toContain(ref);
    const signed = workflow.decide(filled, { ref, decision: "Approved" }).doc;
    expect(select.reviews(signed).find((r) => r.ref === ref)!.approval_status).toBe("Approved");

    // Pre-staging: seeded from what the plan already knows.
    const row = select.prestagingRows(signed).find((r) => r.ref === ref)!;
    expect(row.values.reviewId).toBe(`AREV-${ref.replace(/\./g, "")}`);
    expect(row.values.reviewType).toBe("Additional");
    expect(row.values.assuranceFunction).toBe("Financial Crime Assurance");
    expect(row.values.location).toBe("Global; UK");
    expect(row.complete).toBe(false); // the required fields are still the user's to fill

    // Audit and the decision log carry the rationale.
    expect(signed.audit.some((e) => e.review_ref === ref && e.action === "Review added")).toBe(true);
    expect(select.findReview(signed, ref)!.notes[0].text).toContain("[Rationale]");

    // A version snapshot captures it like any other review.
    const versioned = workflow.saveVersion(signed, { name: "with the new review" }).doc;
    expect(Object.keys(versioned.versions[0].snapshot.reviews)).toContain(ref);
  });

  test("a mandated review is pinned into its go-live quarter and routes to IRR", () => {
    const start = makeInstance([makeReview("1.1")]);
    const { doc, result: ref } = workflow.addReview(start, {
      title: "New regulatory reporting return",
      origin: "Regulatory Assurance",
      assurance_function: "Financial Crime Assurance",
      rationale: "First live submissions land in 2027",
      regulator: "PRA / FCA",
      regulation: "PS7/26",
      rris_ids: "RRIS-10421, RRIS-10422",
      go_live: "2027-08-01",
    });

    const review = select.reviews(doc).find((r) => r.ref === ref)!;
    expect(review.mandated).toBe(true);
    expect(review.staged).toBe(true);
    expect(review.planned_quarter).toBe("Q3");
    expect(review.band).toBe("Mandated");
    expect(review.effective_priority).toBeNull();
    expect(review.route).toBe("IRR");
    expect(review.rris_ids).toEqual(["RRIS-10421", "RRIS-10422"]);

    // Pre-staging is seeded as an externally-mandated review, dated from the go-live.
    const row = select.prestagingRows(doc).find((r) => r.ref === ref)!;
    expect(row.values.reviewType).toBe("Core - Externally mandated");
    expect(row.values.planQuarter).toBe("Q3");

    // Auto-fill leaves the obligation where the regulator put it.
    expect(workflow.autofill(doc).result.quarters[ref]).toBe("Q3");
  });
});

describe("versions", () => {
  test("restore puts every captured field back without rewinding the audit trail", () => {
    const start = makeInstance([makeReview("1.1", { size: "M", quarter: "Q1" })]);
    const { doc: baselined } = workflow.saveVersion(start, { name: "Baseline v1" });
    const auditAfterSave = baselined.audit.length;

    let changed = workflow.setEffortSize(baselined, { ref: "1.1", size: "L" }).doc;
    changed = workflow.setStaged(changed, {
      ref: "1.1",
      staged: false,
      rationale: "descoped after interlock",
    }).doc;
    expect(select.reviews(changed)[0].effort_size).toBe("L");

    const { doc: restored, result } = workflow.restoreVersion(changed, { id: 1 });
    const review = select.reviews(restored)[0];

    expect(result).toBe(1);
    expect(review.effort_size).toBe("M");
    expect(review.staged).toBe(true);
    expect(review.planned_quarter).toBe("Q1");
    // the trail keeps the descope, the restore, and everything before them
    expect(restored.audit.length).toBeGreaterThan(auditAfterSave);
    expect(restored.audit.some((e) => e.action === "Descoped")).toBe(true);
    expect(restored.audit[0].action).toBe("Version restored");
  });
});

describe("the audit trail", () => {
  test("is append-only — the engine exposes no way to amend or remove an entry", () => {
    const commands = Object.keys(workflow).map((k) => k.toLowerCase());
    expect(commands.filter((c) => c.includes("audit"))).toEqual([]);
    expect(commands.some((c) => c.includes("clearlog") || c.includes("deleteaudit"))).toBe(false);
  });

  test("records every decision against the identity in the instance", () => {
    const start = makeInstance([makeReview("1.1")]);
    const { doc } = workflow.setEffortSize(start, { ref: "1.1", size: "L" });

    expect(doc.audit[0]).toMatchObject({
      username: "tester",
      review_ref: "1.1",
      action: "Effort edited",
      detail: "M → L",
    });
  });
});

describe("roles", () => {
  test("a reader cannot change the plan", () => {
    const doc = makeInstance([makeReview("1.1")], { roles: ["Reader"] });
    expect(() => workflow.setEffortSize(doc, { ref: "1.1", size: "L" })).toThrow(/needs the/i);
    expect(() => workflow.decide(doc, { ref: "1.1", decision: "Approved" })).toThrow(/needs the/i);
  });

  test("a planner cannot sign off, and an approver cannot re-shape the plan", () => {
    const planner = makeInstance([makeReview("1.1")], { roles: ["Planner"] });
    expect(() => workflow.decide(planner, { ref: "1.1", decision: "Approved" })).toThrow(
      /needs the Approver/i,
    );

    const approver = makeInstance([makeReview("1.1")], { roles: ["Approver"] });
    expect(() => workflow.autofill(approver)).toThrow(/needs the Planner/i);
  });
});

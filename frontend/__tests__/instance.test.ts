/**
 * The instance document.
 *
 * The hosted JSON is an input from outside the UI, so it is treated like one: a terse
 * document is filled in, a mandated review is pinned whatever the file says, and the
 * shipped instance is checked to load and satisfy the same rules as any other.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { csv, normaliseInstance, select, staging, workflow } from "@/lib/engine";
import type { InstanceDoc } from "@/lib/engine";

const SHIPPED = join(__dirname, "..", "public", "instances", "2027-iap.json");

function shipped(): InstanceDoc {
  return normaliseInstance(JSON.parse(readFileSync(SHIPPED, "utf-8")) as Record<string, unknown>);
}

describe("normalising a hosted document", () => {
  test("a terse review is filled in with workable defaults", () => {
    const doc = normaliseInstance({
      id: "terse",
      reviews: [
        {
          ref: "1.1",
          title: "Only the essentials",
          assurance_function: "Financial Crime Assurance",
          scores: { risk: 4, urgency: 4, coverage_gap: 4, change: 4 },
        },
      ],
    });

    const review = doc.reviews[0];
    expect(review.effort_size).toBe("M");
    expect(review.item).toMatchObject({ staged: false, planned_quarter: null, row_version: 1 });
    expect(review.locations).toEqual([]);
    expect(review.prestaging.values.reviewId).toBe("AREV-11");
    expect(doc.weights).toEqual({ risk: 1, urgency: 1, coverage_gap: 1, change: 1 });
    expect(doc.identity.roles.length).toBeGreaterThan(0);
  });

  test("a mandated review is pinned to its go-live quarter and cannot claim another origin", () => {
    const doc = normaliseInstance({
      id: "pinned",
      reviews: [
        {
          ref: "4.1",
          title: "Mandated",
          assurance_function: "Regulatory Reporting Assurance",
          mandated: true,
          origin: "Risk Radar inputs",
          go_live: "2027-03-18",
        },
      ],
    });

    expect(doc.reviews[0].origin).toBe("Regulatory Assurance");
    expect(doc.reviews[0].item).toMatchObject({ staged: true, planned_quarter: "Q1" });
  });

  test("a document from a future schema is refused rather than half-read", () => {
    expect(() => normaliseInstance({ schema: "iap.instance/99" })).toThrow(/Unsupported/i);
  });

  test("reference values may be plain strings", () => {
    const doc = normaliseInstance({ reference: { location: ["UK", "Global"] } });
    expect(doc.reference.location).toEqual([
      { code: "UK", label: "UK" },
      { code: "Global", label: "Global" },
    ]);
  });
});

describe("the shipped 2027 instance", () => {
  test("loads with the seeded population", () => {
    const doc = shipped();
    expect(doc.reviews).toHaveLength(20);
    expect(doc.plan.year).toBe(2027);
    expect(doc.reviews.filter((r) => r.mandated).map((r) => r.ref)).toEqual(["4.1", "5.1", "7.2"]);
  });

  test("starts with the mandated reviews in the plan and nothing else", () => {
    const doc = shipped();
    const summary = select.planSummary(doc);

    expect(summary.candidates).toBe(20);
    expect(summary.in_scope).toBe(3);
    expect(summary.descoped).toBe(0);
    expect(staging.inPlan(doc.reviews).every((r) => r.mandated)).toBe(true);
  });

  test("auto-fill schedules the whole plan within capacity once everything is staged", () => {
    let doc = shipped();
    for (const ref of doc.reviews.map((r) => r.ref)) {
      doc = workflow.setStaged(doc, { ref, staged: true }).doc;
    }
    const { doc: filled, result } = workflow.autofill(doc);

    expect(result.unplaced).toHaveLength(0);
    for (const load of select.capacityReport(filled).functions) {
      for (const quarter of load.quarters) {
        expect(quarter.demand).toBeLessThanOrEqual(quarter.capacity);
      }
    }
  });

  test("every reference value carried by a review is in the reference lists", () => {
    const impact = select.referenceImpact(shipped());
    expect(impact).toEqual({ taxonomy: [], business: [], location: [] });
  });

  test("exports carry the whole in-plan population", () => {
    const doc = shipped();
    const rows = csv.planRows(doc);

    expect(rows[0][0]).toBe("Assurance function");
    expect(rows).toHaveLength(select.planSummary(doc).in_scope + 1);
    expect(csv.toCsv([["a,b", 'say "hi"']])).toBe('"a,b","say ""hi"""');
  });
});

/**
 * Conventions the codebase relies on, asserted rather than remembered.
 *
 * `.github/copilot-instructions.md` claims every methodology rule is covered by a test.
 * Two of them are not about a calculation, so they are checked here: factor scores are
 * never editable, and rationale is captured inline rather than in a browser dialog.
 * Both are the kind of rule a plausible-looking change quietly breaks.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { select, workflow } from "@/lib/engine";

import { makeInstance, makeReview } from "./factory";

const ROOT = join(__dirname, "..");

const readSource = (relative: string) => readFileSync(join(ROOT, relative), "utf-8");

describe("rule 1 — factor scores are facts, not inputs", () => {
  test("no command assigns to a review's scores", () => {
    const source = readSource("lib/engine/workflow.ts");
    // `addReview` seeds the neutral mid-point through an object literal (`scores: {`).
    // Any *assignment* to scores would be a user-editable path, which is the thing the
    // rule forbids.
    expect(source).not.toMatch(/\.scores\s*=/);
    expect(source).not.toMatch(/scores\.\w+\s*=/);
  });

  test("a command asked to change scores leaves them alone", () => {
    const start = makeInstance([makeReview("1.1", { scores: [2, 2, 2, 2] })]);
    const before = { ...select.findReview(start, "1.1")!.scores! };

    // The Helios pre-staging command takes an open map of changes -- the one place a
    // caller could try to smuggle a score through.
    const { doc } = workflow.updatePrestaging(start, {
      ref: "1.1",
      changes: { risk: "5", scores: "5", reviewLead: "45012345" } as Record<string, string>,
    });

    expect(select.findReview(doc, "1.1")!.scores).toEqual(before);
    expect(select.reviews(doc)[0].effective_priority).toBeCloseTo(2.0);
    // The one legitimate field in that payload still landed.
    expect(doc.reviews[0].prestaging.values.reviewLead).toBe("45012345");
  });
});

describe("rule 15 — no browser dialogs", () => {
  test("no component calls alert, confirm or prompt", () => {
    const components = readdirSync(join(ROOT, "components")).filter((f) => f.endsWith(".tsx"));
    expect(components.length).toBeGreaterThan(0);

    const offenders = components.filter((file) =>
      /\b(window\.)?(alert|confirm|prompt)\s*\(/.test(readSource(join("components", file))),
    );
    expect(offenders).toEqual([]);
  });
});

describe("rule 11 — the audit trail is append-only", () => {
  test("no command in the engine edits or removes an entry", () => {
    const source = readSource("lib/engine/workflow.ts");
    // `unshift` is the single write path; anything that splices, pops or reassigns the
    // trail would be a way to rewrite history.
    expect(source.match(/doc\.audit\.\w+/g) ?? []).toEqual(["doc.audit.unshift"]);
    expect(source).not.toMatch(/\.audit\s*=/);
  });
});

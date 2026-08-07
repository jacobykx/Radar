import { QUARTERS, errorMessage } from "./client";

describe("errorMessage", () => {
  it("returns a FastAPI string detail unchanged", () => {
    // The backend answers a methodology violation with {detail, rule}; the UI shows the
    // rule's own wording rather than inventing its own.
    expect(errorMessage({ detail: "A descope needs a rationale.", rule: "R7" })).toBe(
      "A descope needs a rationale.",
    );
  });

  it("returns the first message from a pydantic validation array", () => {
    expect(
      errorMessage({
        detail: [
          { type: "missing", loc: ["body", "name"], msg: "Field required" },
          { type: "missing", loc: ["body", "note"], msg: "Also required" },
        ],
      }),
    ).toBe("Field required");
  });

  it("falls back when a validation entry carries no msg", () => {
    expect(errorMessage({ detail: [{ type: "missing" }] })).toBe("That change was rejected.");
  });

  it("falls back on an empty detail array", () => {
    expect(errorMessage({ detail: [] })).toBe("That change was rejected.");
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["a bare string", "boom"],
    ["an object with no detail", { message: "boom" }],
  ])("falls back on %s", (_label, input) => {
    expect(errorMessage(input)).toBe("That change was rejected.");
  });
});

describe("QUARTERS", () => {
  it("is the four planning quarters in waterfall order", () => {
    // scheduling.waterfall fills Q1 before Q2; the UI must not reorder them.
    expect(QUARTERS).toEqual(["Q1", "Q2", "Q3", "Q4"]);
  });
});

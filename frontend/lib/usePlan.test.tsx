import { act as reactAct, renderHook, waitFor } from "@testing-library/react";

import { usePlan } from "./usePlan";

/** Resolve each API path to a canned response; anything unlisted fails the spec. */
function stubApi(routes: Record<string, unknown>, status = 200) {
  (global.fetch as jest.Mock).mockImplementation((input: Request | string) => {
    const url = typeof input === "string" ? input : input.url;
    const path = new URL(url, "http://127.0.0.1:8010").pathname;
    if (!(path in routes)) {
      return Promise.reject(new Error(`Unstubbed path: ${path}`));
    }
    return Promise.resolve(
      new Response(JSON.stringify(routes[path]), {
        status,
        headers: { "content-type": "application/json" },
      }),
    );
  });
}

const REVIEWS = [{ ref: "1.1", title: "Sanctions screening" }];
const WEIGHTS = { risk: 0.4, urgency: 0.3, coverage_gap: 0.2, change: 0.1 };
const SUMMARY = { candidates: 20, in_scope: 3 };
const IDENTITY = { username: "local.developer", ad_groups: ["IAP_PLANNER"], roles: ["planner"] };

const HAPPY_ROUTES = {
  "/reviews": REVIEWS,
  "/plan/weights": WEIGHTS,
  "/plan/summary": SUMMARY,
  "/permission": IDENTITY,
};

describe("usePlan", () => {
  it("loads reviews, weights, summary and identity on mount", async () => {
    stubApi(HAPPY_ROUTES);

    const { result } = renderHook(() => usePlan());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.reviews).toEqual(REVIEWS);
    expect(result.current.weights).toEqual(WEIGHTS);
    expect(result.current.summary).toEqual(SUMMARY);
    await waitFor(() => expect(result.current.identity).toEqual(IDENTITY));
    expect(result.current.error).toBeNull();
  });

  it("reports an unreachable backend rather than hanging on the spinner", async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new TypeError("Failed to fetch"));

    const { result } = renderHook(() => usePlan());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toMatch(/Cannot reach the backend/);
  });

  it("surfaces a rejected mutation's message and leaves the plan untouched", async () => {
    stubApi(HAPPY_ROUTES);
    const { result } = renderHook(() => usePlan());
    await waitFor(() => expect(result.current.loading).toBe(false));

    const fetchCallsBefore = (global.fetch as jest.Mock).mock.calls.length;
    let outcome: boolean | undefined;
    await reactAct(async () => {
      outcome = await result.current.act(async () => ({
        error: { detail: "A descope needs a rationale." },
      }));
    });

    // A rejected mutation returns false and must not trigger a resync.
    expect(outcome).toBe(false);
    expect(result.current.error).toBe("A descope needs a rationale.");
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(fetchCallsBefore);
  });

  it("resyncs the plan after a mutation succeeds", async () => {
    stubApi(HAPPY_ROUTES);
    const { result } = renderHook(() => usePlan());
    await waitFor(() => expect(result.current.loading).toBe(false));

    const fetchCallsBefore = (global.fetch as jest.Mock).mock.calls.length;
    let outcome: boolean | undefined;
    await reactAct(async () => {
      outcome = await result.current.act(async () => ({}));
    });

    expect(outcome).toBe(true);
    expect(result.current.error).toBeNull();
    // refresh() re-fetches reviews, weights and summary.
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(fetchCallsBefore + 3);
  });
});

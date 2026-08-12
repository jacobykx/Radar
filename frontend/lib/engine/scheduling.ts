/**
 * Waterfall scheduling.
 *
 * Rule 9: auto-fill packs Q1 -> Q4, placing each review in the *earliest* quarter with
 * remaining FTE, mandated first and then by priority. A team's quarterly FTE is never
 * exceeded; anything that cannot fit is left unscheduled and flagged.
 *
 * Mandated reviews that already hold a quarter -- derived from the regulatory go-live
 * date -- keep it and commit their capacity before anything else is placed. They are
 * pinned by an external obligation, so the scheduler works around them.
 */
import { QUARTERS, type Quarter } from "./constants";
import { fteOf, isInPlan } from "./review";
import { compareForPlan } from "./scoring";
import type { AssuranceFunctionDef, ReviewRecord, Weights } from "./types";

export interface Placement {
  ref: string;
  function: string;
  quarter: Quarter | null;
  fte: number;
  moved: boolean;
}

export interface WaterfallResult {
  placed: Placement[];
  unplaced: Placement[];
  /** Final quarter per review ref, including the pinned ones that were left alone. */
  quarters: Record<string, Quarter | null>;
  summary: string;
}

function isPinned(review: ReviewRecord): boolean {
  return review.mandated && review.item.planned_quarter != null;
}

/**
 * Schedule every in-plan review, one assurance function at a time.
 *
 * Pure: nothing is mutated. The caller persists `result.quarters`.
 */
export function waterfall(
  allReviews: ReviewRecord[],
  capacities: AssuranceFunctionDef[],
  weights: Weights,
): WaterfallResult {
  const reviews = allReviews.filter(isInPlan);
  const placed: Placement[] = [];
  const unplaced: Placement[] = [];
  const quarters: Record<string, Quarter | null> = {};

  for (const capacity of capacities) {
    if (!capacity.is_active) continue;
    const mine = reviews.filter((r) => r.assurance_function === capacity.name);
    if (mine.length === 0) continue;

    const load: Record<Quarter, number> = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 };

    for (const review of mine) {
      if (isPinned(review)) {
        const q = review.item.planned_quarter as Quarter;
        load[q] += fteOf(review);
        quarters[review.ref] = q;
      }
    }

    const queue = mine
      .filter((r) => !isPinned(r))
      .sort((a, b) => compareForPlan(a, b, weights));

    for (const review of queue) {
      const fte = fteOf(review);
      const target =
        QUARTERS.find((q) => load[q] + fte <= capacity.fte_per_quarter) ?? null;
      const placement: Placement = {
        ref: review.ref,
        function: capacity.name,
        quarter: target,
        fte,
        moved: target !== review.item.planned_quarter,
      };
      if (target === null) {
        unplaced.push(placement);
      } else {
        load[target] += fte;
        placed.push(placement);
      }
      quarters[review.ref] = target;
    }
  }

  const moved = placed.filter((p) => p.moved).length;
  const summary =
    `Waterfall Q1→Q4: ${moved} scheduled` +
    (unplaced.length ? `, ${unplaced.length} could not fit` : "");

  return { placed, unplaced, quarters, summary };
}

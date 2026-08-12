/**
 * Priority scoring.
 *
 * Rule 2: priority = (a·risk + b·urgency + c·coverage_gap + d·change) / (a+b+c+d), so
 * the result stays on the 1-5 scale whatever the weights.
 *
 * Rule 3: a user may override the computed priority, but the computed value is never
 * overwritten -- both are stored, and an override without a rationale is refused.
 *
 * Rule 5: mandated reviews are not driver-scored at all.
 */
import { BAND_FLOOR, type Band } from "./constants";
import { RationaleRequired } from "./errors";
import type { ReviewRecord, Scores, Weights } from "./types";

export const PRIORITY_MIN = 0;
export const PRIORITY_MAX = 5;

export function weightTotal(weights: Weights): number {
  return weights.risk + weights.urgency + weights.coverage_gap + weights.change;
}

/**
 * The weighted priority, normalised by the sum of the weights.
 *
 * With every weight at zero the numerator is zero too, so the fallback denominator of
 * 1 yields 0 rather than a division by zero.
 */
export function computedPriority(scores: Scores, weights: Weights): number {
  const total = weightTotal(weights) || 1;
  const weighted =
    scores.risk * weights.risk +
    scores.urgency * weights.urgency +
    scores.coverage_gap * weights.coverage_gap +
    scores.change * weights.change;
  return weighted / total;
}

/**
 * The priority in force: the override if one is set, else the computed value.
 * Mandated reviews are pinned and not driver-scored, so they have no priority.
 */
export function effectivePriority(review: ReviewRecord, weights: Weights): number | null {
  if (review.mandated) return null;
  if (review.item.priority_override != null) return review.item.priority_override;
  if (!review.scores) return null;
  return computedPriority(review.scores, weights);
}

export function band(value: number): Band {
  for (const [floor, name] of BAND_FLOOR) {
    if (value >= floor) return name;
  }
  return "Low";
}

/** Mandated reviews show "Mandated" in place of a priority band (rule 5). */
export function bandOf(review: ReviewRecord, weights: Weights): Band {
  if (review.mandated) return "Mandated";
  const value = effectivePriority(review, weights);
  return value == null ? "Low" : band(value);
}

/** Check an override before it is stored. A rationale is mandatory (rule 3). */
export function validateOverride(value: number, rationale: string | null): [number, string] {
  const text = (rationale || "").trim();
  if (!text) {
    throw new RationaleRequired("A rationale is required to override the computed priority.");
  }
  if (Number.isNaN(value)) {
    throw new RationaleRequired("A numeric priority is required.");
  }
  return [Math.min(PRIORITY_MAX, Math.max(PRIORITY_MIN, value)), text];
}

/** Rank for any priority-ordered list: mandated first, then priority descending. */
export function compareForPlan(a: ReviewRecord, b: ReviewRecord, weights: Weights): number {
  if (a.mandated !== b.mandated) return a.mandated ? -1 : 1;
  const pa = effectivePriority(a, weights) ?? 0;
  const pb = effectivePriority(b, weights) ?? 0;
  if (pa !== pb) return pb - pa;
  return a.ref.localeCompare(b.ref, undefined, { numeric: true });
}

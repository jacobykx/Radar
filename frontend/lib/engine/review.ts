/**
 * Derived properties of a single review record.
 *
 * These are the computed fields the Python build carries on `ReviewView`. Everything
 * downstream -- capacity, scheduling, approval, pre-staging -- reads the plan through
 * `isInPlan`, so the descope cascade holds in one place rather than in every screen.
 */
import { SIZE_FTE } from "./constants";
import type { ReviewRecord } from "./types";

/** FTE required. The per-review override beats the size default (rule 7). */
export function fteOf(review: ReviewRecord): number {
  if (review.fte_override != null) return review.fte_override;
  return SIZE_FTE[review.effort_size];
}

/**
 * Descoped means out of scope *with* a recorded rationale.
 *
 * A review that is merely un-staged is not descoped; the workflow refuses to put a
 * review into that state (decision D1), so it only arises from a seeded, imported or
 * restored record and is reported as an outstanding rationale.
 */
export function isDescoped(review: ReviewRecord): boolean {
  return !review.item.staged && Boolean((review.item.descope_rationale || "").trim());
}

export function rationaleOutstanding(review: ReviewRecord): boolean {
  return !review.item.staged && !review.mandated && !isDescoped(review);
}

/** Staged and not descoped: the population every downstream stage works on. */
export function isInPlan(review: ReviewRecord): boolean {
  return review.item.staged && !isDescoped(review);
}

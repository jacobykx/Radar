/**
 * Staging and descoping.
 *
 * Rule 4: origin and the mandated flag must agree -- a mandated review is always
 * `Regulatory Assurance`.
 *
 * Rule 6: descoping requires a rationale, and a descoped review is removed from
 * staging, capacity, approval, pre-staging and the plan. It is greyed out in Risk
 * Radar, never deleted, because the audit trail must still explain why it left.
 */
import type { Origin } from "./constants";
import { OriginConflict, RationaleRequired } from "./errors";
import { isDescoped, isInPlan, rationaleOutstanding } from "./review";
import type { ReviewRecord } from "./types";

const REGULATORY: Origin = "Regulatory Assurance";

/** Mandated reviews are Regulatory Assurance, and only those are mandated (rule 4). */
export function validateOrigin(origin: Origin, mandated: boolean): void {
  if (mandated && origin !== REGULATORY) {
    throw new OriginConflict(
      `A mandated review must have origin "${REGULATORY}", not "${origin}".`,
    );
  }
  if (!mandated && origin === REGULATORY) {
    throw new OriginConflict(
      `Origin "${REGULATORY}" is reserved for regulator-mandated reviews.`,
    );
  }
}

/** Un-staging a review always requires a recorded rationale (rule 6, decision D1). */
export function validateDescope(rationale: string | null): string {
  const text = (rationale || "").trim();
  if (!text) throw new RationaleRequired("A rationale is required to descope a review.");
  return text;
}

export function inPlan(reviews: ReviewRecord[]): ReviewRecord[] {
  return reviews.filter(isInPlan);
}

export function descoped(reviews: ReviewRecord[]): ReviewRecord[] {
  return reviews.filter(isDescoped);
}

/**
 * Out of the plan with no rationale on record.
 *
 * The workflow refuses to create this state, so anything here arrived by seeding,
 * import or a restored version, and is surfaced as a data-quality report.
 */
export function outstandingRationales(reviews: ReviewRecord[]): ReviewRecord[] {
  return reviews.filter(rationaleOutstanding);
}

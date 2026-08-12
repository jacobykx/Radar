/**
 * Sign-off.
 *
 * Rule 10: exactly one gate per review, routed by type -- IRR for regulator-mandated,
 * RCA for RCA-linked, Standard for everything else. Approve completes the gate; Return
 * requires a comment. Status is Pending / Approved / Returned.
 *
 * The Approval stage also exposes cross-team linkage: where another IRR review, in any
 * team, is driven by the same RRIS obligation or the same regulation, so the same
 * obligation is not signed off twice in ignorance.
 */
import { ROUTE_GATE, type ApprovalRoute, type ApprovalStatus } from "./constants";
import { CommentRequired } from "./errors";
import { isInPlan } from "./review";
import type { ApprovalRecord, ReviewRecord } from "./types";

export function routeOf(review: ReviewRecord): ApprovalRoute {
  if (review.mandated) return "IRR";
  if (review.rca_linked) return "RCA";
  return "Standard";
}

/** The single gate this review must pass. One route, one gate, one decision. */
export function gateOf(review: ReviewRecord): string {
  return ROUTE_GATE[routeOf(review)];
}

/** Approve completes the gate; returning it needs a reason on record (rule 10). */
export function validateDecision(decision: ApprovalStatus, comment: string | null): string {
  const text = (comment || "").trim();
  if (decision === "Returned" && !text) {
    throw new CommentRequired("A comment is required to return a review.");
  }
  if (decision === "Pending") {
    throw new CommentRequired("A sign-off decision must be Approved or Returned.");
  }
  return text;
}

/**
 * The gate in force for a review, created on demand.
 *
 * Routing can change if the review is re-classified -- a re-routed review starts a
 * fresh gate rather than carrying the old decision across.
 */
export function ensureGate(review: ReviewRecord): ApprovalRecord {
  const gate = gateOf(review);
  if (review.approval && review.approval.gate === gate) return review.approval;
  review.approval = {
    route: routeOf(review),
    gate,
    status: "Pending",
    approver: null,
    decided_at: null,
    comment: null,
  };
  return review.approval;
}

export function statusOf(review: ReviewRecord): ApprovalStatus {
  return review.approval?.status ?? "Pending";
}

/** Other in-plan IRR reviews sharing an RRIS ID or the same regulation. */
export function relatedIrr(review: ReviewRecord, others: ReviewRecord[]): ReviewRecord[] {
  const ids = new Set(review.rris_ids);
  const regulation = (review.regulation || "").trim();

  return others.filter((other) => {
    if (other.ref === review.ref || !isInPlan(other)) return false;
    if (routeOf(other) !== "IRR") return false;
    if (other.rris_ids.some((id) => ids.has(id))) return true;
    return Boolean(regulation) && (other.regulation || "").trim() === regulation;
  });
}

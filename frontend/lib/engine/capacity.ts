/**
 * Capacity.
 *
 * Rule 7: effort size S/M/L requires 2/3/4 FTE by default; a per-review FTE overrides it.
 *
 * Rule 8: capacity is FTE per quarter per assurance function. A review scheduled in a
 * quarter consumes its FTE for that quarter. Mandated demand commits capacity first;
 * the rest fills what remains.
 */
import { QUARTERS, type Quarter } from "./constants";
import { fteOf, isInPlan } from "./review";
import type { AssuranceFunctionDef, ReviewRecord } from "./types";

export interface QuarterLoad {
  quarter: Quarter;
  capacity: number;
  demand: number;
  headroom: number;
  over: boolean;
}

export interface FunctionLoad {
  function: string;
  fte_per_quarter: number;
  quarters: QuarterLoad[];
  unscheduled_fte: number;
  over: boolean;
}

export interface BottomUpFill {
  annual_fte_quarters: number;
  mandated_fte: number;
  additional_fte: number;
  remaining_after_mandated: number;
  headroom: number;
  over: boolean;
}

export function annualFteQuarters(fn: AssuranceFunctionDef): number {
  return fn.fte_per_quarter * QUARTERS.length;
}

/** FTE drawn from one function in one quarter by the reviews in the plan. */
export function quarterDemand(
  reviews: ReviewRecord[],
  functionName: string,
  quarter: Quarter,
): number {
  return reviews
    .filter(
      (r) =>
        isInPlan(r) &&
        r.assurance_function === functionName &&
        r.item.planned_quarter === quarter,
    )
    .reduce((sum, r) => sum + fteOf(r), 0);
}

export function functionLoad(
  reviews: ReviewRecord[],
  capacity: AssuranceFunctionDef,
): FunctionLoad {
  const quarters = QUARTERS.map((q) => {
    const demand = quarterDemand(reviews, capacity.name, q);
    return {
      quarter: q,
      capacity: capacity.fte_per_quarter,
      demand,
      headroom: capacity.fte_per_quarter - demand,
      over: demand > capacity.fte_per_quarter,
    };
  });
  const unscheduled = reviews
    .filter(
      (r) =>
        isInPlan(r) && r.assurance_function === capacity.name && r.item.planned_quarter == null,
    )
    .reduce((sum, r) => sum + fteOf(r), 0);

  return {
    function: capacity.name,
    fte_per_quarter: capacity.fte_per_quarter,
    quarters,
    unscheduled_fte: unscheduled,
    over: quarters.some((q) => q.over),
  };
}

/** Mandated demand committed first, the remainder available to everything else. */
export function bottomUpFill(
  reviews: ReviewRecord[],
  capacities: AssuranceFunctionDef[],
): BottomUpFill {
  const annual = capacities
    .filter((c) => c.is_active)
    .reduce((sum, c) => sum + annualFteQuarters(c), 0);
  const planned = reviews.filter(isInPlan);
  const mandated = planned.filter((r) => r.mandated).reduce((s, r) => s + fteOf(r), 0);
  const additional = planned.filter((r) => !r.mandated).reduce((s, r) => s + fteOf(r), 0);
  const remaining = annual - mandated;

  return {
    annual_fte_quarters: annual,
    mandated_fte: mandated,
    additional_fte: additional,
    remaining_after_mandated: remaining,
    headroom: remaining - additional,
    over: remaining - additional < 0,
  };
}

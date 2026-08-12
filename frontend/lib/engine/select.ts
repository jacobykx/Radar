/**
 * Read models.
 *
 * Every screen reads the instance through this module rather than walking the document
 * itself, so a rule such as "descoped reviews are not in the approval population" is
 * stated once. The payload shapes match the FastAPI service's responses field for
 * field -- the UI's contract does not change when the data starts coming from there.
 */
import * as approvalRules from "./approval";
import * as capacityRules from "./capacity";
import {
  APPROVAL_ROUTES,
  APPROVAL_STATUSES,
  ORIGINS,
  QUARTERS,
  SIZE_DAYS,
  type ApprovalRoute,
  type ApprovalStatus,
  type Band,
  type EffortSize,
  type Origin,
  type Quarter,
  type ReferenceKind,
} from "./constants";
import * as helios from "./helios";
import { fteOf, isDescoped, isInPlan, rationaleOutstanding } from "./review";
import * as scoring from "./scoring";
import * as staging from "./staging";
import type {
  ApprovalRecord,
  InstanceDoc,
  Note,
  ReviewRecord,
  StewardRecord,
  Weights,
} from "./types";

/** Everything a screen can know about one review. */
export interface Review {
  ref: string;
  title: string;
  origin: Origin;
  mandated: boolean;
  taxonomy_code: string | null;
  taxonomy_label: string | null;
  assurance_function: string;
  sub_team: string | null;
  business: string | null;
  locations: string[];
  effort_size: EffortSize;
  effort_days: number;
  fte: number;
  fte_override: number | null;
  regulator: string | null;
  regulation: string | null;
  rris_ids: string[];
  rca_linked: boolean;
  go_live: string | null;
  scores: ReviewRecord["scores"];
  computed_priority: number | null;
  priority_override: number | null;
  priority_override_rationale: string | null;
  effective_priority: number | null;
  band: Band;
  staged: boolean;
  descoped: boolean;
  rationale_outstanding: boolean;
  descope_rationale: string | null;
  planned_quarter: Quarter | null;
  row_version: number;
  route: ApprovalRoute;
  approval_status: ApprovalStatus;
  approval: ApprovalRecord | null;
  steward: StewardRecord | null;
  notes: Note[];
}

export function taxonomyLabels(doc: InstanceDoc): Record<string, string> {
  return Object.fromEntries(doc.reference.taxonomy.map((t) => [t.code, t.label]));
}

export function activeCapacities(doc: InstanceDoc) {
  return doc.assurance_functions.filter((f) => f.is_active);
}

export function findReview(doc: InstanceDoc, ref: string): ReviewRecord | undefined {
  return doc.reviews.find((r) => r.ref === ref);
}

export function reviewOut(
  review: ReviewRecord,
  weights: Weights,
  taxonomy: Record<string, string> = {},
): Review {
  const computed =
    review.scores && !review.mandated ? scoring.computedPriority(review.scores, weights) : null;

  return {
    ref: review.ref,
    title: review.title,
    origin: review.origin,
    mandated: review.mandated,
    taxonomy_code: review.taxonomy_code,
    taxonomy_label: review.taxonomy_code
      ? (taxonomy[review.taxonomy_code] ?? review.taxonomy_code)
      : null,
    assurance_function: review.assurance_function,
    sub_team: review.sub_team,
    business: review.business,
    locations: [...review.locations],
    effort_size: review.effort_size,
    effort_days: SIZE_DAYS[review.effort_size],
    fte: fteOf(review),
    fte_override: review.fte_override,
    regulator: review.regulator,
    regulation: review.regulation,
    rris_ids: [...review.rris_ids],
    rca_linked: review.rca_linked,
    go_live: review.go_live,
    scores: review.scores,
    computed_priority: computed,
    priority_override: review.item.priority_override,
    priority_override_rationale: review.item.priority_override_rationale,
    effective_priority: scoring.effectivePriority(review, weights),
    band: scoring.bandOf(review, weights),
    staged: review.item.staged,
    descoped: isDescoped(review),
    rationale_outstanding: rationaleOutstanding(review),
    descope_rationale: review.item.descope_rationale,
    planned_quarter: review.item.planned_quarter,
    row_version: review.item.row_version,
    route: approvalRules.routeOf(review),
    approval_status: approvalRules.statusOf(review),
    approval: review.approval,
    steward: review.steward,
    notes: review.notes,
  };
}

export function reviews(doc: InstanceDoc): Review[] {
  const taxonomy = taxonomyLabels(doc);
  return [...doc.reviews]
    .sort((a, b) => a.ref.localeCompare(b.ref, undefined, { numeric: true }))
    .map((r) => reviewOut(r, doc.weights, taxonomy));
}

// ------------------------------------------------------------------------------- plan

export interface PlanSummary {
  candidates: number;
  in_scope: number;
  descoped: number;
  scheduled: number;
  unscheduled: number;
  outstanding_rationales: number;
  prestaging_ready: number;
  annual_fte_quarters: number;
  used_fte: number;
  utilisation_pct: number;
  fte_by_quarter: Record<Quarter, number>;
}

/** The funnel and headline numbers on the dashboard strip. */
export function planSummary(doc: InstanceDoc): PlanSummary {
  const planned = staging.inPlan(doc.reviews);
  const annual = activeCapacities(doc).reduce(
    (sum, c) => sum + capacityRules.annualFteQuarters(c),
    0,
  );
  const used = planned.reduce((sum, r) => sum + fteOf(r), 0);

  return {
    candidates: doc.reviews.length,
    in_scope: planned.length,
    descoped: staging.descoped(doc.reviews).length,
    scheduled: planned.filter((r) => r.item.planned_quarter).length,
    unscheduled: planned.filter((r) => !r.item.planned_quarter).length,
    outstanding_rationales: staging.outstandingRationales(doc.reviews).length,
    prestaging_ready: planned.filter((r) =>
      helios.isComplete(prestagingValues(r)),
    ).length,
    annual_fte_quarters: annual,
    used_fte: used,
    utilisation_pct: annual ? Math.round((used / annual) * 100) : 0,
    fte_by_quarter: Object.fromEntries(
      QUARTERS.map((q) => [
        q,
        planned.filter((r) => r.item.planned_quarter === q).reduce((s, r) => s + fteOf(r), 0),
      ]),
    ) as Record<Quarter, number>,
  };
}

export interface CapacityReport {
  scope: {
    label: string;
    candidate_reviews: number;
    fte_per_quarter: number;
    annual_fte_quarters: number;
  };
  bottom_up: capacityRules.BottomUpFill;
  aggregate: { quarter: Quarter; capacity: number; demand: number; over: boolean; warn: boolean }[];
  unscheduled_count: number;
  functions: capacityRules.FunctionLoad[];
}

/**
 * Capacity for the selected scope.
 *
 * Two granularities, deliberately. `aggregate` is the roll-up the staging screen shows;
 * `functions` is the per-function detail, which is the granularity the waterfall
 * actually enforces against -- one function's spare FTE cannot cover another's.
 */
export function capacityReport(doc: InstanceDoc, team?: string): CapacityReport {
  const scoped = doc.reviews.filter((r) => !team || r.assurance_function === team);
  const capacities = activeCapacities(doc).filter((c) => !team || c.name === team);
  const fill = capacityRules.bottomUpFill(scoped, capacities);
  const ftePerQuarter = capacities.reduce((sum, c) => sum + c.fte_per_quarter, 0);
  const planned = scoped.filter(isInPlan);

  const aggregate = QUARTERS.map((quarter) => {
    const demand = planned
      .filter((r) => r.item.planned_quarter === quarter)
      .reduce((sum, r) => sum + fteOf(r), 0);
    const over = demand > ftePerQuarter;
    return { quarter, capacity: ftePerQuarter, demand, over, warn: !over && demand > ftePerQuarter * 0.85 };
  });

  return {
    scope: {
      label: team || "Portfolio (all teams)",
      candidate_reviews: scoped.filter((r) => !isDescoped(r)).length,
      fte_per_quarter: ftePerQuarter,
      annual_fte_quarters: fill.annual_fte_quarters,
    },
    bottom_up: fill,
    aggregate,
    unscheduled_count: planned.filter((r) => !r.item.planned_quarter).length,
    functions: capacities.map((c) => capacityRules.functionLoad(scoped, c)),
  };
}

export interface ShapedGroup {
  function: string;
  total_fte: number;
  by_quarter: Record<Quarter, number>;
  reviews: {
    ref: string;
    title: string;
    mandated: boolean;
    size: EffortSize;
    fte: number;
    business: string | null;
    locations: string[];
    quarter: Quarter | null;
    band: Band;
  }[];
}

/** The Gantt: in-plan reviews grouped by assurance function, laid out by quarter. */
export function shapedPlan(doc: InstanceDoc): { quarters: Quarter[]; groups: ShapedGroup[] } {
  const planned = staging
    .inPlan(doc.reviews)
    .sort((a, b) => scoring.compareForPlan(a, b, doc.weights));

  const groups = new Map<string, ReviewRecord[]>();
  for (const review of planned) {
    const bucket = groups.get(review.assurance_function) ?? [];
    bucket.push(review);
    groups.set(review.assurance_function, bucket);
  }

  return {
    quarters: [...QUARTERS],
    groups: [...groups.entries()].map(([name, items]) => ({
      function: name,
      total_fte: items.reduce((sum, r) => sum + fteOf(r), 0),
      by_quarter: Object.fromEntries(
        QUARTERS.map((q) => [
          q,
          items.filter((r) => r.item.planned_quarter === q).reduce((s, r) => s + fteOf(r), 0),
        ]),
      ) as Record<Quarter, number>,
      reviews: items.map((r) => ({
        ref: r.ref,
        title: r.title,
        mandated: r.mandated,
        size: r.effort_size,
        fte: fteOf(r),
        business: r.business,
        locations: [...r.locations],
        quarter: r.item.planned_quarter,
        band: scoring.bandOf(r, doc.weights),
      })),
    })),
  };
}

// --------------------------------------------------------------------------- approval

export interface ApprovalFilters {
  team?: string;
  business?: string;
  location?: string;
  route?: string;
  status?: string;
}

/** Rule 6: descoped reviews are not in the approval population at all. */
export function approvalScope(doc: InstanceDoc, filters: ApprovalFilters = {}): ReviewRecord[] {
  return doc.reviews
    .filter((review) => {
      if (!isInPlan(review)) return false;
      if (filters.team && review.assurance_function !== filters.team) return false;
      if (filters.business && review.business !== filters.business) return false;
      if (filters.location && !review.locations.includes(filters.location)) return false;
      if (filters.route && approvalRules.routeOf(review) !== filters.route) return false;
      if (filters.status && approvalRules.statusOf(review) !== filters.status) return false;
      return true;
    })
    .sort((a, b) => a.ref.localeCompare(b.ref, undefined, { numeric: true }));
}

export interface ApprovalDashboard {
  total: number;
  by_status: Record<ApprovalStatus, number>;
  approved_pct: number;
  by_origin: Record<string, number>;
  by_route: Record<ApprovalRoute, { total: number; approved: number }>;
  linkage: Record<string, string[]>;
}

/** Cards that recalculate to whatever is in the filtered view. */
export function approvalDashboard(
  doc: InstanceDoc,
  scope: ReviewRecord[],
): ApprovalDashboard {
  const statuses = scope.map(approvalRules.statusOf);
  const approved = statuses.filter((s) => s === "Approved").length;
  const everything = staging.inPlan(doc.reviews);

  return {
    total: scope.length,
    by_status: Object.fromEntries(
      APPROVAL_STATUSES.map((s) => [s, statuses.filter((x) => x === s).length]),
    ) as Record<ApprovalStatus, number>,
    approved_pct: scope.length ? Math.round((approved / scope.length) * 100) : 0,
    by_origin: Object.fromEntries(
      ORIGINS.map((origin) => [origin, scope.filter((r) => r.origin === origin).length]),
    ),
    by_route: Object.fromEntries(
      APPROVAL_ROUTES.map((route) => {
        const inRoute = scope.filter((r) => approvalRules.routeOf(r) === route);
        return [
          route,
          {
            total: inRoute.length,
            approved: inRoute.filter((r) => approvalRules.statusOf(r) === "Approved").length,
          },
        ];
      }),
    ) as Record<ApprovalRoute, { total: number; approved: number }>,
    linkage: Object.fromEntries(
      scope
        .filter((r) => approvalRules.routeOf(r) === "IRR")
        .map((r) => [r.ref, approvalRules.relatedIrr(r, everything).map((x) => x.ref)]),
    ),
  };
}

export function approvalView(doc: InstanceDoc, filters: ApprovalFilters = {}) {
  const scope = approvalScope(doc, filters);
  const taxonomy = taxonomyLabels(doc);
  return {
    dashboard: approvalDashboard(doc, scope),
    reviews: scope.map((r) => reviewOut(r, doc.weights, taxonomy)),
  };
}

// ------------------------------------------------------------------------ pre-staging

/** Stored values plus the two things the record never stores: locations and the derived fields. */
export function prestagingValues(review: ReviewRecord): Record<string, string> {
  return {
    ...review.prestaging.values,
    location: review.locations.join("; "),
    ...helios.derivedValues(review.prestaging.target_start),
  };
}

export interface PrestagingRow {
  ref: string;
  title: string;
  mandated: boolean;
  target_start: string | null;
  values: Record<string, string>;
  complete: boolean;
  missing: string[];
}

export function prestagingRows(doc: InstanceDoc): PrestagingRow[] {
  return staging.inPlan(doc.reviews).map((review) => {
    const values = prestagingValues(review);
    return {
      ref: review.ref,
      title: review.title,
      mandated: review.mandated,
      target_start: review.prestaging.target_start,
      values,
      complete: helios.isComplete(values),
      missing: helios.missingFields(values),
    };
  });
}

export function prestagingSpec(doc: InstanceDoc) {
  return {
    fields: helios.HELIOS_FIELDS,
    business: doc.reference.business.map((b) => b.label),
    location: doc.reference.location.map((l) => l.label),
  };
}

// --------------------------------------------------------------------- governance

/** Values still carried by reviews that are no longer in the reference lists (risk R1). */
export function referenceImpact(doc: InstanceDoc): Record<ReferenceKind, string[]> {
  const taxonomy = new Set(doc.reference.taxonomy.map((t) => t.code));
  const businesses = new Set(doc.reference.business.map((b) => b.label));
  const locations = new Set(doc.reference.location.map((l) => l.label));

  const unique = (values: (string | null)[]) =>
    [...new Set(values.filter((v): v is string => Boolean(v)))].sort();

  return {
    taxonomy: unique(doc.reviews.map((r) => r.taxonomy_code)).filter((c) => !taxonomy.has(c)),
    business: unique(doc.reviews.map((r) => r.business)).filter((b) => !businesses.has(b)),
    location: unique(doc.reviews.flatMap((r) => r.locations)).filter((l) => !locations.has(l)),
  };
}

export function outstandingRationales(doc: InstanceDoc) {
  return staging.outstandingRationales(doc.reviews).map((r) => ({
    ref: r.ref,
    title: r.title,
    assurance_function: r.assurance_function,
    effective_priority: scoring.effectivePriority(r, doc.weights),
  }));
}

export function versionRows(doc: InstanceDoc) {
  return [...doc.versions].sort((a, b) => b.id - a.id);
}

/**
 * Test fixtures.
 *
 * Sane defaults, so each test overrides only the thing it is about -- the same shape
 * as `backend/tests/conftest.py`.
 */
import { normaliseInstance } from "@/lib/engine";
import type {
  AssuranceFunctionDef,
  InstanceDoc,
  Quarter,
  ReviewRecord,
  Role,
  Weights,
} from "@/lib/engine";

export const WEIGHTS: Weights = { risk: 1, urgency: 1, coverage_gap: 1, change: 1 };

export interface ReviewOptions {
  mandated?: boolean;
  origin?: ReviewRecord["origin"];
  function?: string;
  size?: ReviewRecord["effort_size"];
  scores?: [number, number, number, number] | null;
  staged?: boolean;
  quarter?: Quarter | null;
  fte_override?: number | null;
  rca_linked?: boolean;
  rris_ids?: string[];
  regulation?: string | null;
  locations?: string[];
  descope_rationale?: string | null;
  priority_override?: number | null;
  go_live?: string | null;
}

export function makeReview(ref = "1.1", options: ReviewOptions = {}): ReviewRecord {
  const mandated = options.mandated ?? false;
  const [risk, urgency, coverage_gap, change] = options.scores ?? [4, 4, 4, 4];

  return {
    ref,
    title: `Review ${ref}`,
    origin: options.origin ?? (mandated ? "Regulatory Assurance" : "Risk Radar inputs"),
    mandated,
    taxonomy_code: "fincrime",
    assurance_function: options.function ?? "Financial Crime Assurance",
    sub_team: null,
    business: null,
    locations: options.locations ?? [],
    effort_size: options.size ?? "M",
    fte_override: options.fte_override ?? null,
    regulator: null,
    regulation: options.regulation ?? null,
    rris_ids: options.rris_ids ?? [],
    rca_linked: options.rca_linked ?? false,
    go_live: options.go_live ?? null,
    is_custom: false,
    scores:
      options.scores === null
        ? null
        : { risk, urgency, coverage_gap, change, source: "test" },
    item: {
      staged: options.staged ?? true,
      planned_quarter: options.quarter ?? null,
      priority_override: options.priority_override ?? null,
      priority_override_rationale: options.priority_override == null ? null : "because",
      descope_rationale: options.descope_rationale ?? null,
      row_version: 1,
    },
    prestaging: { target_start: null, values: {} },
    approval: null,
    steward: null,
    notes: [],
  };
}

export function makeFunction(
  name = "Financial Crime Assurance",
  ftePerQuarter = 10,
): AssuranceFunctionDef {
  return { name, fte_per_quarter: ftePerQuarter, is_active: ftePerQuarter > 0 };
}

export function makeInstance(
  reviews: ReviewRecord[] = [makeReview()],
  options: {
    functions?: AssuranceFunctionDef[];
    weights?: Weights;
    roles?: Role[];
  } = {},
): InstanceDoc {
  const functions =
    options.functions ??
    [...new Set(reviews.map((r) => r.assurance_function))].map((name) => makeFunction(name));

  return normaliseInstance({
    schema: "iap.instance/1",
    id: "test",
    plan: { year: 2027, name: "2027 test plan" },
    identity: {
      username: "tester",
      ad_groups: [],
      roles: options.roles ?? ["Planner", "Approver", "Admin"],
    },
    reference: {
      taxonomy: [{ code: "fincrime", label: "Financial crime & AML" }],
      business: [{ code: "CIB", label: "CIB" }],
      location: [
        { code: "Global", label: "Global" },
        { code: "UK", label: "UK" },
        { code: "USA", label: "USA" },
      ],
    },
    assurance_functions: functions,
    sub_teams: {},
    weights: options.weights ?? WEIGHTS,
    reviews,
    audit: [],
    versions: [],
    revision: 0,
  });
}

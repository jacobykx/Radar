/**
 * Loading an instance.
 *
 * The instance is a JSON document fetched over HTTP -- by default the one served from
 * `public/instances/`, but `NEXT_PUBLIC_INSTANCE_URL` points the UI at any URL that
 * returns the same shape. That is the seam the productionised build replaces with the
 * planning API: swap this module, and the workflow above it is untouched.
 *
 * A hosted document may be terse. Everything that has a sensible default -- plan item
 * state, pre-staging values, empty collections -- is filled in here, once, so no rule
 * downstream has to cope with a half-populated record.
 */
import { INSTANCE_SCHEMA } from "./types";
import { DomainError } from "./errors";
import { quarterFromDate } from "./helios";
import type {
  AssuranceFunctionDef,
  AuditEntry,
  Identity,
  InstanceDoc,
  PlanItem,
  PrestagingRecord,
  ReferenceValue,
  ReviewRecord,
  Weights,
} from "./types";
import type { EffortSize, Origin, Quarter, ReferenceKind, Role } from "./constants";

export const DEFAULT_INSTANCE_URL =
  process.env.NEXT_PUBLIC_INSTANCE_URL ?? "/instances/2027-iap.json";

export const DEFAULT_WEIGHTS: Weights = { risk: 1, urgency: 1, coverage_gap: 1, change: 1 };

type Raw = Record<string, unknown>;

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function strOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function num(value: unknown, fallback: number): number {
  return typeof value === "number" && !Number.isNaN(value) ? value : fallback;
}

function numOrNull(value: unknown): number | null {
  return typeof value === "number" && !Number.isNaN(value) ? value : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function strings(value: unknown): string[] {
  return list(value).filter((v): v is string => typeof v === "string");
}

/**
 * Pre-staging defaults for a review.
 *
 * Only the fields that can be derived from what the plan already knows. The rest are
 * blank on purpose -- the completeness flag exists to show what is still missing.
 */
export function prestagingDefaults(review: ReviewRecord): PrestagingRecord {
  return {
    target_start: review.mandated ? review.go_live : null,
    values: {
      reviewId: `AREV-${review.ref.replace(/\./g, "")}`,
      title: review.title,
      reviewType: review.mandated ? "Core - Externally mandated" : "Additional",
      assuranceFunction: review.assurance_function,
      reviewTeam: review.sub_team ?? "",
      business: review.business ?? "",
      riskFlags: "NA",
      esgFlag: "No",
      status: "Planned",
    },
  };
}

function normaliseItem(raw: Raw, mandated: boolean, goLive: string | null): PlanItem {
  const quarter = str(raw.planned_quarter) as Quarter | "";
  return {
    // Rule 5: mandated reviews are pinned into the plan, in their go-live quarter.
    staged: typeof raw.staged === "boolean" ? raw.staged : mandated,
    planned_quarter: quarter || (mandated ? quarterFromDate(goLive) : null),
    priority_override: numOrNull(raw.priority_override),
    priority_override_rationale: strOrNull(raw.priority_override_rationale),
    descope_rationale: strOrNull(raw.descope_rationale),
    row_version: num(raw.row_version, 1),
  };
}

function normaliseReview(raw: Raw): ReviewRecord {
  const mandated = raw.mandated === true;
  const goLive = strOrNull(raw.go_live);
  const review: ReviewRecord = {
    ref: str(raw.ref),
    title: str(raw.title),
    // Rule 4: origin and the mandated flag cannot disagree, whatever the document says.
    origin: (mandated ? "Regulatory Assurance" : str(raw.origin, "Risk Radar inputs")) as Origin,
    mandated,
    taxonomy_code: strOrNull(raw.taxonomy_code),
    assurance_function: str(raw.assurance_function),
    sub_team: strOrNull(raw.sub_team),
    business: strOrNull(raw.business),
    locations: strings(raw.locations),
    effort_size: (str(raw.effort_size, "M") as EffortSize) || "M",
    fte_override: numOrNull(raw.fte_override),
    regulator: strOrNull(raw.regulator),
    regulation: strOrNull(raw.regulation),
    rris_ids: strings(raw.rris_ids),
    rca_linked: raw.rca_linked === true,
    go_live: goLive,
    is_custom: raw.is_custom === true,
    scores: raw.scores
      ? {
          risk: num((raw.scores as Raw).risk, 0),
          urgency: num((raw.scores as Raw).urgency, 0),
          coverage_gap: num((raw.scores as Raw).coverage_gap, 0),
          change: num((raw.scores as Raw).change, 0),
          as_at: strOrNull((raw.scores as Raw).as_at) ?? undefined,
          source: strOrNull((raw.scores as Raw).source) ?? undefined,
        }
      : null,
    item: normaliseItem((raw.item as Raw) ?? {}, mandated, goLive),
    prestaging: { target_start: null, values: {} },
    approval: (raw.approval as ReviewRecord["approval"]) ?? null,
    steward: (raw.steward as ReviewRecord["steward"]) ?? null,
    notes: list(raw.notes) as ReviewRecord["notes"],
  };

  const defaults = prestagingDefaults(review);
  const supplied = (raw.prestaging as Raw | undefined) ?? {};
  review.prestaging = {
    target_start: strOrNull(supplied.target_start) ?? defaults.target_start,
    values: { ...defaults.values, ...((supplied.values as Record<string, string>) ?? {}) },
  };

  return review;
}

function normaliseReference(raw: unknown): Record<ReferenceKind, ReferenceValue[]> {
  const source = (raw as Raw) ?? {};
  const read = (kind: ReferenceKind): ReferenceValue[] =>
    list(source[kind]).map((entry) => {
      if (typeof entry === "string") return { code: entry, label: entry };
      const value = entry as Raw;
      const code = str(value.code) || str(value.label);
      return { code, label: str(value.label) || code };
    });
  return { taxonomy: read("taxonomy"), business: read("business"), location: read("location") };
}

function normaliseIdentity(raw: unknown): Identity {
  const source = (raw as Raw) ?? {};
  const roles = strings(source.roles) as Role[];
  return {
    username: str(source.username, "poc.user"),
    ad_groups: strings(source.ad_groups),
    roles: roles.length ? roles : ["Planner", "Approver", "Admin"],
  };
}

/** Turn a hosted document into the fully-populated instance the workflow expects. */
export function normaliseInstance(raw: Raw): InstanceDoc {
  if (raw.schema && raw.schema !== INSTANCE_SCHEMA) {
    throw new DomainError(
      `Unsupported instance schema "${String(raw.schema)}" — this build reads ${INSTANCE_SCHEMA}.`,
    );
  }

  const plan = (raw.plan as Raw) ?? {};
  const weights = (raw.weights as Raw) ?? {};
  const functions = list(raw.assurance_functions).map((entry) => {
    const value = entry as Raw;
    const fte = num(value.fte_per_quarter, 0);
    return {
      name: str(value.name),
      fte_per_quarter: fte,
      is_active: typeof value.is_active === "boolean" ? value.is_active : fte > 0,
    } satisfies AssuranceFunctionDef;
  });

  const reviews = list(raw.reviews).map((entry) => normaliseReview(entry as Raw));
  const audit = list(raw.audit) as AuditEntry[];

  return {
    schema: INSTANCE_SCHEMA,
    id: str(raw.id, "instance"),
    plan: { year: num(plan.year, new Date().getFullYear()), name: str(plan.name, "Annual plan") },
    identity: normaliseIdentity(raw.identity),
    reference: normaliseReference(raw.reference),
    assurance_functions: functions,
    sub_teams: (raw.sub_teams as Record<string, string[]>) ?? {},
    weights: {
      risk: num(weights.risk, DEFAULT_WEIGHTS.risk),
      urgency: num(weights.urgency, DEFAULT_WEIGHTS.urgency),
      coverage_gap: num(weights.coverage_gap, DEFAULT_WEIGHTS.coverage_gap),
      change: num(weights.change, DEFAULT_WEIGHTS.change),
    },
    reviews,
    audit,
    versions: list(raw.versions) as InstanceDoc["versions"],
    revision: num(raw.revision, 0),
  };
}

/** Fetch and normalise the hosted instance. */
export async function fetchInstance(url: string = DEFAULT_INSTANCE_URL): Promise<InstanceDoc> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new DomainError(`Could not load the instance from ${url} (HTTP ${response.status}).`);
  }
  return normaliseInstance((await response.json()) as Raw);
}

export function cloneInstance(doc: InstanceDoc): InstanceDoc {
  return JSON.parse(JSON.stringify(doc)) as InstanceDoc;
}

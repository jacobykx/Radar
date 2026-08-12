/**
 * The instance document.
 *
 * One JSON document is the whole world: reference data, capacity, the candidate
 * reviews and every piece of planning state a user can change. The UI loads it,
 * applies the workflow rules to it, and can hand it back out again -- so the file that
 * is hosted and the file that is exported are the same shape.
 *
 * Keys are snake_case throughout, matching the names the FastAPI service uses, so the
 * same document can be served by that API when the POC is productionised.
 */
import type {
  ApprovalRoute,
  ApprovalStatus,
  EffortSize,
  Origin,
  Quarter,
  ReferenceKind,
  Role,
} from "./constants";

export const INSTANCE_SCHEMA = "iap.instance/1";

export interface Weights {
  risk: number;
  urgency: number;
  coverage_gap: number;
  change: number;
}

/** The four factor scores: read-only facts from the upstream scoring engine. */
export interface Scores {
  risk: number;
  urgency: number;
  coverage_gap: number;
  change: number;
  as_at?: string;
  source?: string;
}

export interface ReferenceValue {
  code: string;
  label: string;
}

export interface AssuranceFunctionDef {
  name: string;
  fte_per_quarter: number;
  is_active: boolean;
}

export interface PlanItem {
  staged: boolean;
  planned_quarter: Quarter | null;
  priority_override: number | null;
  priority_override_rationale: string | null;
  descope_rationale: string | null;
  row_version: number;
}

export interface PrestagingRecord {
  target_start: string | null;
  values: Record<string, string>;
}

export interface ApprovalRecord {
  route: ApprovalRoute;
  gate: string;
  status: ApprovalStatus;
  approver: string | null;
  decided_at: string | null;
  comment: string | null;
}

export interface StewardRecord {
  steward_name: string;
  recorded_by: string;
  recorded_at: string;
}

export interface Note {
  author: string;
  text: string;
  created_at: string;
}

/** One candidate review: the facts about it, plus the planning state carried against it. */
export interface ReviewRecord {
  ref: string;
  title: string;
  origin: Origin;
  mandated: boolean;
  taxonomy_code: string | null;
  assurance_function: string;
  sub_team: string | null;
  business: string | null;
  locations: string[];
  effort_size: EffortSize;
  fte_override: number | null;
  regulator: string | null;
  regulation: string | null;
  rris_ids: string[];
  rca_linked: boolean;
  go_live: string | null;
  is_custom: boolean;
  scores: Scores | null;
  item: PlanItem;
  prestaging: PrestagingRecord;
  approval: ApprovalRecord | null;
  steward: StewardRecord | null;
  notes: Note[];
}

/** Append-only. There is no operation in the engine that edits or removes an entry. */
export interface AuditEntry {
  id: number;
  review_ref: string | null;
  action: string;
  detail: string;
  username: string;
  created_at: string;
}

export interface PlanVersion {
  id: number;
  name: string;
  note: string;
  author: string;
  created_at: string;
  staged_count: number;
  snapshot: VersionSnapshot;
}

/** Everything a planner can change. The audit trail is deliberately not in here. */
export interface VersionSnapshot {
  weights: Weights;
  reviews: Record<
    string,
    {
      effort_size: EffortSize;
      fte_override: number | null;
      business: string | null;
      locations: string[];
      item: Omit<PlanItem, "row_version">;
      prestaging: PrestagingRecord;
      approval: ApprovalRecord | null;
      steward: StewardRecord | null;
    }
  >;
}

export interface Identity {
  username: string;
  ad_groups: string[];
  roles: Role[];
}

export interface InstanceDoc {
  schema: typeof INSTANCE_SCHEMA;
  id: string;
  plan: { year: number; name: string };
  identity: Identity;
  reference: Record<ReferenceKind, ReferenceValue[]>;
  assurance_functions: AssuranceFunctionDef[];
  sub_teams: Record<string, string[]>;
  weights: Weights;
  reviews: ReviewRecord[];
  audit: AuditEntry[];
  versions: PlanVersion[];
  /** Bumped on every mutation, so a stale tab can tell it is behind. */
  revision: number;
}

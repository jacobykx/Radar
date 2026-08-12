/**
 * The workflow.
 *
 * Every change a user can make to the plan is a command in this module. Commands are
 * pure over the instance document: they take the current document, apply the
 * methodology, and return a new one. Nothing here touches React, `fetch` or
 * `localStorage`, so the rules can be tested exactly as the Python services layer is.
 *
 * Two invariants hold for all of them:
 *   - a rule violation throws a `DomainError` and the document is left untouched;
 *   - a successful change appends to the audit trail in the same step as the change.
 */
import * as approvalRules from "./approval";
import type {
  ApprovalStatus,
  EffortSize,
  Origin,
  Quarter,
  ReferenceKind,
  Role,
} from "./constants";
import { DomainError, Forbidden, RationaleRequired, StaleWrite } from "./errors";
import * as helios from "./helios";
import { cloneInstance, prestagingDefaults } from "./instance";
import { fteOf } from "./review";
import * as scheduling from "./scheduling";
import * as scoring from "./scoring";
import * as select from "./select";
import * as staging from "./staging";
import type {
  AuditEntry,
  InstanceDoc,
  ReferenceValue,
  ReviewRecord,
  VersionSnapshot,
  Weights,
} from "./types";

export interface CommandResult<R = null> {
  doc: InstanceDoc;
  result: R;
}

const now = () => new Date().toISOString();

/**
 * Role check.
 *
 * An authentication gateway supplies the identity and the productionised API enforces
 * this server-side. In the POC the identity travels in the instance document, so this
 * demonstrates the rule; it is not a security control.
 */
function requireRole(doc: InstanceDoc, ...roles: Role[]): string {
  const held = new Set(doc.identity.roles);
  if (!roles.some((role) => held.has(role))) {
    throw new Forbidden(
      `This action needs the ${roles.join(" or ")} role; you hold ${
        doc.identity.roles.join(", ") || "no roles"
      }.`,
    );
  }
  return doc.identity.username;
}

/** Append one audit entry. There is deliberately no way to amend or remove one. */
function record(
  doc: InstanceDoc,
  entry: { username: string; action: string; detail?: string; ref?: string | null },
): void {
  const next: AuditEntry = {
    id: (doc.audit[0]?.id ?? 0) + 1,
    review_ref: entry.ref ?? null,
    action: entry.action,
    detail: entry.detail ?? "",
    username: entry.username,
    created_at: now(),
  };
  doc.audit.unshift(next);
  doc.revision += 1;
}

/** Work on a copy, so a rule that throws half-way leaves the caller's document intact. */
function edit(doc: InstanceDoc): InstanceDoc {
  return cloneInstance(doc);
}

function reviewOrThrow(doc: InstanceDoc, ref: string): ReviewRecord {
  const review = select.findReview(doc, ref);
  if (!review) throw new DomainError(`No review with ref "${ref}".`, "NotFound", 404);
  return review;
}

/** Optimistic concurrency (risk R2): refuse a write made against stale state. */
function checkVersion(review: ReviewRecord, expected?: number | null): void {
  if (expected != null && expected !== review.item.row_version) {
    throw new StaleWrite(
      `This review changed since you loaded it (version ${review.item.row_version}, you sent ` +
        `${expected}). Reload and try again.`,
    );
  }
}

function touch(review: ReviewRecord): void {
  review.item.row_version += 1;
}

function addNoteTo(review: ReviewRecord, author: string, text: string): void {
  review.notes.push({ author, text, created_at: now() });
}

// ------------------------------------------------------------------------------ plan

export function setWeights(doc: InstanceDoc, weights: Weights): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  next.weights = { ...weights };
  record(next, {
    username,
    action: "Priority weights changed",
    detail:
      `risk ${weights.risk}, urgency ${weights.urgency}, ` +
      `coverage ${weights.coverage_gap}, change ${weights.change}`,
  });
  return { doc: next, result: null };
}

/** Rule 9: waterfall Q1→Q4 and persist the result, reporting what would not fit. */
export function autofill(doc: InstanceDoc): CommandResult<scheduling.WaterfallResult> {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const result = scheduling.waterfall(
    next.reviews,
    select.activeCapacities(next),
    next.weights,
  );

  for (const [ref, quarter] of Object.entries(result.quarters)) {
    const review = select.findReview(next, ref);
    if (!review) continue;
    review.item.planned_quarter = quarter;
    touch(review);
  }

  record(next, { username, action: "Quarters auto-filled", detail: result.summary });
  return { doc: next, result };
}

export function clearQuarters(doc: InstanceDoc): CommandResult<number> {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  let cleared = 0;
  for (const review of next.reviews) {
    if (review.item.planned_quarter) {
      review.item.planned_quarter = null;
      touch(review);
      cleared += 1;
    }
  }
  record(next, {
    username,
    action: "Quarters cleared",
    detail: `${cleared} review(s) unscheduled`,
  });
  return { doc: next, result: cleared };
}

// ---------------------------------------------------------------------------- reviews

/**
 * Stage a review in, or descope it out.
 *
 * Rule 6: descoping always requires a rationale, and the workflow refuses the state
 * rather than recording it and flagging it afterwards (decision D1).
 */
export function setStaged(
  doc: InstanceDoc,
  args: { ref: string; staged: boolean; rationale?: string | null; row_version?: number | null },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  checkVersion(review, args.row_version);

  if (args.staged) {
    review.item.staged = true;
    review.item.descope_rationale = null;
    record(next, {
      username,
      ref: review.ref,
      action: "Staged IN",
      detail: "Selected for the plan",
    });
  } else {
    const text = staging.validateDescope(args.rationale ?? null);
    review.item.staged = false;
    review.item.descope_rationale = text;
    review.item.planned_quarter = null;
    addNoteTo(review, username, `[Descoped] ${text}`);
    record(next, { username, ref: review.ref, action: "Descoped", detail: text });
  }

  touch(review);
  return { doc: next, result: null };
}

/** Rule 3: store the override beside the computed value, never over it. */
export function setPriorityOverride(
  doc: InstanceDoc,
  args: { ref: string; value: number; rationale?: string | null; row_version?: number | null },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  checkVersion(review, args.row_version);
  const [clamped, text] = scoring.validateOverride(args.value, args.rationale ?? null);

  const computed = review.scores ? scoring.computedPriority(review.scores, next.weights) : null;
  review.item.priority_override = clamped;
  review.item.priority_override_rationale = text;
  touch(review);

  addNoteTo(review, username, `[Priority override → ${clamped.toFixed(2)}] ${text}`);
  record(next, {
    username,
    ref: review.ref,
    action: "Priority override",
    detail:
      computed == null
        ? `set ${clamped.toFixed(2)}. Rationale: ${text}`
        : `computed ${computed.toFixed(2)} → set ${clamped.toFixed(2)}. Rationale: ${text}`,
  });
  return { doc: next, result: null };
}

export function clearPriorityOverride(
  doc: InstanceDoc,
  args: { ref: string; row_version?: number | null },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  checkVersion(review, args.row_version);

  review.item.priority_override = null;
  review.item.priority_override_rationale = null;
  touch(review);

  const computed = review.scores ? scoring.computedPriority(review.scores, next.weights) : null;
  record(next, {
    username,
    ref: review.ref,
    action: "Priority override",
    detail:
      computed == null ? "reset to computed" : `reset to computed ${computed.toFixed(2)}`,
  });
  return { doc: next, result: null };
}

export function setQuarter(
  doc: InstanceDoc,
  args: { ref: string; quarter: Quarter | null; row_version?: number | null },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  checkVersion(review, args.row_version);

  const previous = review.item.planned_quarter ?? "—";
  review.item.planned_quarter = args.quarter;
  touch(review);
  record(next, {
    username,
    ref: review.ref,
    action: "Planned quarter",
    detail: `${previous} → ${args.quarter ?? "—"}`,
  });
  return { doc: next, result: null };
}

export function setEffortSize(
  doc: InstanceDoc,
  args: { ref: string; size: EffortSize },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  const previous = review.effort_size;
  if (previous === args.size) return { doc, result: null };

  review.effort_size = args.size;
  record(next, {
    username,
    ref: review.ref,
    action: "Effort edited",
    detail: `${previous} → ${args.size}`,
  });
  return { doc: next, result: null };
}

export function setFte(
  doc: InstanceDoc,
  args: { ref: string; fte: number | null },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  const previous = fteOf(review);
  review.fte_override = args.fte;
  const current = fteOf(review);
  if (previous === current) return { doc, result: null };

  record(next, {
    username,
    ref: review.ref,
    action: "FTE edited",
    detail: `${previous} → ${current} FTE`,
  });
  return { doc: next, result: null };
}

/** Rule 13: replace the multi-location set, ordered by the reference list. */
export function setLocations(
  doc: InstanceDoc,
  args: { ref: string; locations: string[] },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);

  const reference = next.reference.location.map((l) => l.label);
  const unique = [...new Set(args.locations.map((l) => l.trim()).filter(Boolean))];
  const ordered = reference
    .filter((l) => unique.includes(l))
    .concat(unique.filter((l) => !reference.includes(l)));

  const previous = review.locations;
  review.locations = ordered;
  if (previous.join("; ") === ordered.join("; ")) return { doc, result: null };

  record(next, {
    username,
    ref: review.ref,
    action: "Locations updated",
    detail: `${previous.join("; ") || "(none)"} → ${ordered.join("; ") || "(none)"}`,
  });
  return { doc: next, result: null };
}

/** Rule 14: applies to Risk Radar inputs -- name, who recorded it, and when. */
export function recordSteward(
  doc: InstanceDoc,
  args: { ref: string; steward_name: string },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const name = (args.steward_name || "").trim();
  if (!name) throw new RationaleRequired("The risk steward's name is required.");

  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  review.steward = { steward_name: name, recorded_by: username, recorded_at: now() };
  record(next, {
    username,
    ref: review.ref,
    action: "Risk steward consulted",
    detail: `${name} (recorded by ${username})`,
  });
  return { doc: next, result: null };
}

export function addNote(
  doc: InstanceDoc,
  args: { ref: string; text: string },
): CommandResult {
  const username = requireRole(doc, "Planner", "Approver", "Admin");
  const text = (args.text || "").trim();
  if (!text) throw new RationaleRequired("A note cannot be empty.");

  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  addNoteTo(review, username, text);
  record(next, { username, ref: review.ref, action: "Note", detail: text });
  return { doc: next, result: null };
}

export interface NewReview {
  title: string;
  origin: Origin;
  assurance_function: string;
  sub_team?: string | null;
  taxonomy_code?: string | null;
  business?: string | null;
  locations?: string[];
  effort_size?: EffortSize;
  rationale?: string | null;
  regulator?: string | null;
  regulation?: string | null;
  rris_ids?: string | null;
  go_live?: string | null;
}

/** Both add-forms. Mandated reviews are pinned and always Regulatory Assurance. */
export function addReview(doc: InstanceDoc, body: NewReview): CommandResult<string> {
  const username = requireRole(doc, "Planner", "Admin");
  const mandated = body.origin === "Regulatory Assurance";
  staging.validateOrigin(body.origin, mandated);

  const rationale = (body.rationale || "").trim();
  if (!rationale) throw new RationaleRequired("A rationale is required to add a review.");
  if (!(body.title || "").trim()) throw new DomainError("A title is required.");

  const next = edit(doc);
  const taken = new Set(next.reviews.map((r) => r.ref));
  let n = 1;
  while (taken.has(`EXT-${n}`)) n += 1;
  const ref = `EXT-${n}`;

  const review: ReviewRecord = {
    ref,
    title: body.title.trim(),
    origin: body.origin,
    mandated,
    taxonomy_code: body.taxonomy_code ?? null,
    assurance_function: body.assurance_function,
    sub_team: body.sub_team ?? null,
    business: body.business ?? null,
    locations: [],
    effort_size: body.effort_size ?? "M",
    fte_override: null,
    regulator: body.regulator ?? null,
    regulation: body.regulation ?? null,
    rris_ids: (body.rris_ids || "")
      .split(/[,;]/)
      .map((s) => s.trim())
      .filter(Boolean),
    rca_linked: false,
    go_live: body.go_live ?? null,
    is_custom: true,
    // A new review is not driver-scored by a user: it starts at the neutral mid-point
    // and is restated by the scoring engine.
    scores: { risk: 3, urgency: 3, coverage_gap: 3, change: 3, as_at: now(), source: "manual-default" },
    item: {
      // Mandated reviews are pinned into the plan; risk-led ones enter the backlog unstaged.
      staged: mandated,
      planned_quarter: mandated ? helios.quarterFromDate(body.go_live ?? null) : null,
      priority_override: null,
      priority_override_rationale: null,
      descope_rationale: null,
      row_version: 1,
    },
    prestaging: { target_start: null, values: {} },
    approval: null,
    steward: null,
    notes: [],
  };
  review.prestaging = prestagingDefaults(review);
  next.reviews.push(review);

  if (body.locations?.length) {
    const reference = next.reference.location.map((l) => l.label);
    const unique = [...new Set(body.locations.filter(Boolean))];
    review.locations = reference
      .filter((l) => unique.includes(l))
      .concat(unique.filter((l) => !reference.includes(l)));
  }

  addNoteTo(review, username, `[Rationale] ${rationale}`);
  record(next, {
    username,
    ref,
    action: "Review added",
    detail: `${body.origin} — ${review.title} — rationale: ${rationale}`,
  });
  return { doc: next, result: ref };
}

// --------------------------------------------------------------------------- approval

/** Approve completes the gate; returning it requires a comment (rule 10). */
export function decide(
  doc: InstanceDoc,
  args: { ref: string; decision: ApprovalStatus; comment?: string | null },
): CommandResult {
  const username = requireRole(doc, "Approver", "Admin");
  const text = approvalRules.validateDecision(args.decision, args.comment ?? null);

  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);
  const gate = approvalRules.ensureGate(review);
  gate.status = args.decision;
  gate.approver = username;
  gate.decided_at = now();
  gate.comment = text || null;

  record(next, {
    username,
    ref: review.ref,
    action: `${gate.gate} — ${args.decision === "Approved" ? "approved" : "returned"}`,
    detail: `${username}${text ? `: ${text}` : ""}`,
  });
  return { doc: next, result: null };
}

/** "Approve all in view": everything matching the supplied filter. */
export function bulkApprove(
  doc: InstanceDoc,
  filters: select.ApprovalFilters = {},
): CommandResult<string[]> {
  requireRole(doc, "Approver", "Admin");
  const refs = select.approvalScope(doc, filters).map((r) => r.ref);
  let next = doc;
  for (const ref of refs) {
    next = decide(next, { ref, decision: "Approved", comment: null }).doc;
  }
  return { doc: next, result: refs };
}

// ------------------------------------------------------------------------ pre-staging

export function updatePrestaging(
  doc: InstanceDoc,
  args: { ref: string; changes: Record<string, string> },
): CommandResult {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const review = reviewOrThrow(next, args.ref);

  for (const [key, value] of Object.entries(args.changes)) {
    // Derived from Target Start Date; never accepted from a caller.
    if (helios.DERIVED_FIELDS.includes(key)) continue;
    if (!helios.FIELDS_BY_KEY[key]) continue;
    helios.validateValue(key, value);

    if (key === "targetStart") review.prestaging.target_start = value || null;
    review.prestaging.values[key] = value;
    record(next, {
      username,
      ref: review.ref,
      action: "Pre-staging edit",
      detail: `${key} → ${value || "(cleared)"}`,
    });
  }
  return { doc: next, result: null };
}

// ---------------------------------------------------------------------- reference data

/** Replace a list. Values still in use are reported, never silently dropped (risk R1). */
export function replaceReference(
  doc: InstanceDoc,
  args: { kind: ReferenceKind; entries: ReferenceValue[] },
): CommandResult {
  const username = requireRole(doc, "Admin");
  const next = edit(doc);
  const entries = args.entries
    .map((e) => ({ code: (e.code || e.label || "").trim(), label: (e.label || e.code || "").trim() }))
    .filter((e) => e.code);
  next.reference[args.kind] = entries;
  record(next, {
    username,
    action: "Reference data updated",
    detail: `${args.kind}: ${entries.length} value(s)`,
  });
  return { doc: next, result: null };
}

// --------------------------------------------------------------------------- versions

function capture(doc: InstanceDoc): VersionSnapshot {
  return {
    weights: { ...doc.weights },
    reviews: Object.fromEntries(
      doc.reviews.map((r) => [
        r.ref,
        {
          effort_size: r.effort_size,
          fte_override: r.fte_override,
          business: r.business,
          locations: [...r.locations],
          item: {
            staged: r.item.staged,
            planned_quarter: r.item.planned_quarter,
            priority_override: r.item.priority_override,
            priority_override_rationale: r.item.priority_override_rationale,
            descope_rationale: r.item.descope_rationale,
          },
          prestaging: JSON.parse(JSON.stringify(r.prestaging)) as ReviewRecord["prestaging"],
          approval: r.approval ? { ...r.approval } : null,
          steward: r.steward ? { ...r.steward } : null,
        },
      ]),
    ),
  };
}

export function saveVersion(
  doc: InstanceDoc,
  args: { name: string; note?: string },
): CommandResult<number> {
  const username = requireRole(doc, "Planner", "Admin");
  const next = edit(doc);
  const snapshot = capture(next);
  const staged = Object.values(snapshot.reviews).filter((r) => r.item.staged).length;
  const id = Math.max(0, ...next.versions.map((v) => v.id)) + 1;

  next.versions.push({
    id,
    name: (args.name || "").trim() || "Untitled version",
    note: (args.note || "").trim(),
    author: username,
    created_at: now(),
    staged_count: staged,
    snapshot,
  });
  record(next, {
    username,
    action: "Version saved",
    detail: `"${next.versions[next.versions.length - 1].name}" — ${staged} staged`,
  });
  return { doc: next, result: id };
}

/**
 * Put every captured field back. Reviews absent from the snapshot are left alone, and
 * the audit trail is not rewound -- restoring is itself an audited event (rule 12).
 */
export function restoreVersion(doc: InstanceDoc, args: { id: number }): CommandResult<number> {
  const username = requireRole(doc, "Admin");
  const next = edit(doc);
  const version = next.versions.find((v) => v.id === args.id);
  if (!version) throw new DomainError(`No version with id ${args.id}.`, "NotFound", 404);

  let restored = 0;
  for (const [ref, saved] of Object.entries(version.snapshot.reviews)) {
    const review = select.findReview(next, ref);
    if (!review) continue;

    review.effort_size = saved.effort_size;
    review.fte_override = saved.fte_override;
    review.business = saved.business;
    review.locations = [...saved.locations];
    review.item = { ...saved.item, row_version: review.item.row_version + 1 };
    review.prestaging = JSON.parse(JSON.stringify(saved.prestaging)) as ReviewRecord["prestaging"];
    review.approval = saved.approval ? { ...saved.approval } : null;
    review.steward = saved.steward ? { ...saved.steward } : null;
    restored += 1;
  }
  next.weights = { ...version.snapshot.weights };

  record(next, {
    username,
    action: "Version restored",
    detail: `"${version.name}" — ${restored} review(s)`,
  });
  return { doc: next, result: restored };
}

export function deleteVersion(doc: InstanceDoc, args: { id: number }): CommandResult {
  const username = requireRole(doc, "Admin");
  const next = edit(doc);
  const version = next.versions.find((v) => v.id === args.id);
  if (!version) throw new DomainError(`No version with id ${args.id}.`, "NotFound", 404);

  next.versions = next.versions.filter((v) => v.id !== args.id);
  record(next, { username, action: "Version deleted", detail: `"${version.name}"` });
  return { doc: next, result: null };
}

/**
 * Helios pre-staging.
 *
 * The field set comes from the shared Planning Key Fields spec; only fields present
 * there are captured and exported. Plan/IAP quarter and year are derived from the
 * Target Start Date and are never user-entered. A review is Helios-ready once every
 * required field carries a value.
 */
import type { Quarter } from "./constants";
import { DomainError } from "./errors";

export const ASSURANCE_FUNCTIONS: string[] = [
  "Financial Crime Assurance",
  "Regulatory Compliance Assurance",
  "United States Assurance",
  "China Assurance",
  "Traded Risk Assurance",
  "Treasury Risk Assurance",
  "Regulatory Reporting Assurance",
  "Group Insurance Assurance",
  "Wholesale Credit Risk Unit Assurance",
  "Continental Europe Assurance",
  "Singapore Assurance",
  "Malaysia Assurance",
  "Innovation Bank Assurance",
];

export const REVIEW_TEAMS: string[] = [
  "Hong Kong (FC)", "UK (FC)", "CIB (FC)", "Fraud", "AML", "Sanctions", "IWPB (FC)",
  "IWPB (RC)", "MSS (RC)", "CIB (RC)", "CIB Asia & MENAT (RC)", "Hong Kong (RC)", "UK (RC)",
  "China", "Continental Europe", "Singapore", "Innovation Bank Assurance", "Global", "LATAM",
  "USA", "ASP", "Canada", "Europe", "DBS & GF", "MENAT", "UKRFB",
];

/** Where the field comes from -- drives the legend on the pre-staging screen. */
export type FieldGroup = "existing" | "change" | "system";

export interface HeliosField {
  key: string;
  label: string;
  type: "text" | "textarea" | "select" | "date" | "derived" | "multiloc";
  group: FieldGroup;
  allowed: string[] | null;
  hint: string | null;
  full_width: boolean;
  required: boolean;
}

function field(
  key: string,
  label: string,
  type: HeliosField["type"],
  extra: Partial<Omit<HeliosField, "key" | "label" | "type">> = {},
): HeliosField {
  return {
    key,
    label,
    type,
    group: extra.group ?? "existing",
    allowed: extra.allowed ?? null,
    hint: extra.hint ?? null,
    full_width: extra.full_width ?? false,
    required: false,
  };
}

/** Without these, the review is not Helios-ready. */
export const REQUIRED_FIELDS: string[] = [
  "reviewType", "reviewCategory", "assuranceFunction", "reviewLead", "reviewTeam",
  "targetStart", "scopeRationale",
];

export const DERIVED_FIELDS: string[] = ["planQuarter", "iapQuarter", "planYear", "iapYear"];

/** Reference-data-backed lists are resolved at render time, not frozen here. */
export const REFERENCE_BACKED: Record<string, "business" | "location"> = {
  business: "business",
  location: "location",
};

export const HELIOS_FIELDS: HeliosField[] = [
  field("reviewId", "Lookup Key (Review ID)", "text"),
  field("title", "Title", "text", { full_width: true }),
  field("reviewDetail", "Review Detail (Review Rationale)", "textarea", {
    group: "change",
    full_width: true,
  }),
  field("reviewType", "Review Type", "select", {
    allowed: [
      "Core - Externally mandated", "Core - Internally mandated", "Additional", "Opinion Paper",
    ],
  }),
  field("reviewCategory", "Review Category", "select", {
    allowed: ["Global", "Regional", "Country", "Single - Market Review", "Multi - Market Review"],
  }),
  field("assuranceFunction", "Assurance Function", "select", {
    group: "change",
    allowed: ASSURANCE_FUNCTIONS,
  }),
  field("reviewLead", "Review Lead (Staff ID)", "text"),
  field("reviewTeam", "Review Team", "select", { allowed: REVIEW_TEAMS }),
  field("business", "Business", "select", { hint: "KBD Reference Data Mapper" }),
  field("location", "Location(s)", "multiloc", {
    hint: "KBD Reference Data Mapper · multi-select",
  }),
  field("legalEntity", "Legal Entity", "text", { hint: "KBD Reference Data Mapper" }),
  field("riskTaxonomy", "Risk Taxonomy", "text", { hint: "Group Risk Taxonomy" }),
  field("riskFlags", "Risk Flags", "select", {
    allowed: ["FRB/DPA", "Swap Dealer", "Volcker", "NA"],
  }),
  field("esgFlag", "ESG Flag", "select", { allowed: ["Yes", "No"] }),
  field("conductOutcome", "Conduct Outcome", "text", { hint: "See Assurance Reference Data" }),
  field("scopeRationale", "Review Scope and Rationale", "textarea", { full_width: true }),
  field("gscCoverage", "GSC Coverage", "text"),
  field("status", "Assurance Review Status", "select", {
    group: "change",
    allowed: ["Planned"],
  }),
  field("targetStart", "Target Start Date", "date"),
  field("planQuarter", "Plan Quarter", "derived", { group: "system" }),
  field("iapQuarter", "IAP Quarter", "derived", { group: "system" }),
  field("planYear", "Plan Year", "derived", { group: "system" }),
  field("iapYear", "IAP Year", "derived", { group: "system" }),
  field("materialControls", "Material Controls", "text"),
  field("auditability", "Auditability", "text"),
  field("cancellationCategory", "Cancellation Category", "text", { group: "change" }),
  field("reasonCancellation", "Reason for Cancellation", "textarea", { full_width: true }),
].map((f) => ({ ...f, required: REQUIRED_FIELDS.includes(f.key) }));

export const FIELDS_BY_KEY: Record<string, HeliosField> = Object.fromEntries(
  HELIOS_FIELDS.map((f) => [f.key, f]),
);

export const EXPORT_HEADER: string[] = HELIOS_FIELDS.map((f) => f.label);

/** Plan/IAP quarter and year follow the Target Start Date. Nothing else sets them. */
export function derivedValues(targetStart: string | null): Record<string, string> {
  if (!targetStart) return { planQuarter: "", iapQuarter: "", planYear: "", iapYear: "" };
  const date = new Date(`${targetStart}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return { planQuarter: "", iapQuarter: "", planYear: "", iapYear: "" };
  }
  const quarter: Quarter = `Q${Math.floor(date.getUTCMonth() / 3) + 1}` as Quarter;
  const year = String(date.getUTCFullYear());
  return { planQuarter: quarter, iapQuarter: quarter, planYear: year, iapYear: year };
}

export function missingFields(values: Record<string, string>): string[] {
  return REQUIRED_FIELDS.filter((k) => !String(values[k] ?? "").trim());
}

export function isComplete(values: Record<string, string>): boolean {
  return missingFields(values).length === 0;
}

/** Reject a value the Helios spec does not allow, rather than exporting it. */
export function validateValue(key: string, value: string): void {
  const spec = FIELDS_BY_KEY[key];
  if (!spec) return;
  if (spec.allowed && value && !spec.allowed.includes(value)) {
    throw new DomainError(`"${value}" is not an allowed value for ${spec.label}.`);
  }
}

/** One export line, in spec order, with the derived fields resolved. */
export function exportRow(
  values: Record<string, string>,
  targetStart: string | null,
): string[] {
  const derived = derivedValues(targetStart);
  return HELIOS_FIELDS.map((f) =>
    f.type === "derived" ? (derived[f.key] ?? "") : String(values[f.key] ?? ""),
  );
}

/** The quarter a mandated review is pinned to, from its regulatory go-live date. */
export function quarterFromDate(iso: string | null): Quarter | null {
  if (!iso) return null;
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  return `Q${Math.floor(date.getUTCMonth() / 3) + 1}` as Quarter;
}

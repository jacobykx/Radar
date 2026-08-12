/**
 * Domain constants and enumerations.
 *
 * These are assurance-methodology facts, not configuration: changing a value here
 * changes the methodology. In the POC the whole methodology runs in the browser, so
 * this file is the single place those facts are stated.
 */

export const QUARTERS = ["Q1", "Q2", "Q3", "Q4"] as const;
export type Quarter = (typeof QUARTERS)[number];

export type EffortSize = "S" | "M" | "L";
export const EFFORT_SIZES: EffortSize[] = ["S", "M", "L"];

/** Assurance days by effort size. */
export const SIZE_DAYS: Record<EffortSize, number> = { S: 60, M: 90, L: 120 };

/** FTE required to run a review of each size, before any per-review override. */
export const SIZE_FTE: Record<EffortSize, number> = { S: 2, M: 3, L: 4 };

/** Where a review came from. Mandated reviews are always Regulatory Assurance. */
export type Origin = "Regulatory Assurance" | "Risk Assurance" | "Risk Radar inputs";
export const ORIGINS: Origin[] = ["Regulatory Assurance", "Risk Assurance", "Risk Radar inputs"];

export type ApprovalRoute = "IRR" | "RCA" | "Standard";
export const APPROVAL_ROUTES: ApprovalRoute[] = ["IRR", "RCA", "Standard"];

/** The single sign-off gate on each route. */
export const ROUTE_GATE: Record<ApprovalRoute, string> = {
  IRR: "IRR sign-off",
  RCA: "RCA owner sign-off",
  Standard: "1LOD / L2 sign-off",
};

export type ApprovalStatus = "Pending" | "Approved" | "Returned";
export const APPROVAL_STATUSES: ApprovalStatus[] = ["Pending", "Approved", "Returned"];

export type Band = "Critical" | "High" | "Medium" | "Low" | "Mandated";

/** Lower bound of each priority band on the 1-5 scale. */
export const BAND_FLOOR: [number, Band][] = [
  [4.3, "Critical"],
  [3.7, "High"],
  [3.0, "Medium"],
];

export type ReferenceKind = "taxonomy" | "business" | "location";
export const REFERENCE_KINDS: ReferenceKind[] = ["taxonomy", "business", "location"];

/**
 * Roles, as FRAME's Auth Service would supply them from AD groups.
 *
 * In the POC the identity comes from the instance document, so these checks demonstrate
 * the rule rather than enforce it -- anything running in a browser can be edited by the
 * person running it. The productionised build enforces them server-side.
 */
export type Role = "Planner" | "Approver" | "Admin" | "Reader";

/**
 * Exports.
 *
 * The prototype's exports were server-rendered CSV downloads. With the workflow in the
 * browser there is nothing to ask a server for -- the same rows are built here and
 * handed to the user as a Blob. Column orders match the FastAPI service's exports, so
 * a spreadsheet built against one still opens against the other.
 */
import { SIZE_DAYS } from "./constants";
import { EXPORT_HEADER, exportRow } from "./helios";
import * as select from "./select";
import type { InstanceDoc } from "./types";

/** RFC 4180 quoting: double the quotes, wrap anything with a delimiter or newline. */
export function toCsv(rows: (string | number | null | undefined)[][]): string {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          const text = cell == null ? "" : String(cell);
          return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
        })
        .join(","),
    )
    .join("\r\n");
}

export function planRows(doc: InstanceDoc): string[][] {
  const rows: string[][] = [
    ["Assurance function", "Ref", "Review", "Mandated", "Size", "Days", "FTE", "Quarter",
     "Business", "Location", "Band"],
  ];
  for (const group of select.shapedPlan(doc).groups) {
    for (const r of group.reviews) {
      rows.push([
        group.function, r.ref, r.title, r.mandated ? "Yes" : "No", r.size,
        String(SIZE_DAYS[r.size]), String(r.fte), r.quarter ?? "", r.business ?? "",
        r.locations.join("; "), r.band,
      ]);
    }
  }
  return rows;
}

export function approvalRows(doc: InstanceDoc, filters: select.ApprovalFilters = {}): string[][] {
  const scope = select.approvalScope(doc, filters);
  const linkage = select.approvalDashboard(doc, scope).linkage;
  const taxonomy = select.taxonomyLabels(doc);

  const rows: string[][] = [
    ["Ref", "Review", "Origin", "Route", "Team", "Sub-team", "Business", "Location", "Quarter",
     "Size", "FTE", "Priority", "Mandated", "Regulator", "Regulation", "RRIS IDs",
     "Risk taxonomy", "Related IRR refs", "Approval status", "Gate", "Signed off by",
     "Signed off on", "Comment"],
  ];
  for (const record of scope) {
    const r = select.reviewOut(record, doc.weights, taxonomy);
    rows.push([
      r.ref, r.title, r.origin, r.route, r.assurance_function, r.sub_team ?? "",
      r.business ?? "", r.locations.join("; "), r.planned_quarter ?? "", r.effort_size,
      String(r.fte), r.mandated ? "—" : (r.effective_priority?.toFixed(2) ?? ""),
      r.mandated ? "Yes" : "No", r.regulator ?? "", r.regulation ?? "", r.rris_ids.join("; "),
      r.taxonomy_label ?? "", (linkage[r.ref] ?? []).join("; "), r.approval_status,
      r.approval?.gate ?? "", r.approval?.approver ?? "",
      r.approval?.decided_at ? r.approval.decided_at.slice(0, 10) : "",
      r.approval?.comment ?? "",
    ]);
  }
  return rows;
}

export function prestagingCsvRows(doc: InstanceDoc): string[][] {
  return [
    EXPORT_HEADER,
    ...select.prestagingRows(doc).map((row) => exportRow(row.values, row.target_start)),
  ];
}

export function auditRows(doc: InstanceDoc): string[][] {
  return [
    ["When", "Who", "Ref", "Action", "Detail"],
    ...doc.audit.map((e) => [e.created_at, e.username, e.review_ref ?? "—", e.action, e.detail]),
  ];
}

/** Trigger a download in the browser. No-op anywhere without a DOM. */
export function download(filename: string, content: string, type: string): void {
  if (typeof document === "undefined") return;
  const url = URL.createObjectURL(new Blob([content], { type: `${type};charset=utf-8` }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function downloadCsv(filename: string, rows: (string | number | null)[][]): void {
  download(filename, toCsv(rows), "text/csv");
}

/**
 * Hand the working plan back out as an instance document.
 *
 * This is what closes the loop on a JSON-hosted instance: edit the plan in the UI,
 * export it, host that file, and the next session starts where this one finished.
 */
export function downloadInstance(doc: InstanceDoc): void {
  download(`${doc.id}.json`, JSON.stringify(doc, null, 2), "application/json");
}

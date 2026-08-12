"use client";

import { useMemo, useState } from "react";

import { csv, select, workflow } from "@/lib/engine";
import type { PlanState } from "@/lib/usePlan";

/**
 * Helios pre-staging.
 *
 * The field set comes from `lib/engine/helios` — the Planning Key Fields spec, stated
 * once. Plan/IAP quarter and year are derived there too, which is why they render as
 * read-only however this screen is used.
 */
export function Prestaging({ plan }: { plan: PlanState }) {
  const { doc, run } = plan;
  const [open, setOpen] = useState<string | null>(null);

  const spec = useMemo(() => (doc ? select.prestagingSpec(doc) : null), [doc]);
  const records = useMemo(() => (doc ? select.prestagingRows(doc) : []), [doc]);

  const save = (ref: string, key: string, value: string) =>
    run((current) => workflow.updatePrestaging(current, { ref, changes: { [key]: value } }));

  if (!spec || !doc) return <div className="panel muted">Loading the Helios field spec…</div>;

  const ready = records.filter((r) => r.complete).length;

  return (
    <div className="panel">
      <h3>
        Helios pre-staging enrichment{" "}
        <span className="sub">— capture the Helios attributes for each in-plan review.</span>
      </h3>
      <div className="rowactions">
        <span className="small">
          <b>
            {ready} of {records.length}
          </b>{" "}
          Helios-ready
        </span>
        <span className="muted small">
          Plan / IAP quarter and year are derived from Target Start Date and cannot be typed.
        </span>
        <button
          className="btn primary"
          onClick={() =>
            csv.downloadCsv(
              `${doc.plan.year}_IAP_Helios_prestaging.csv`,
              csv.prestagingCsvRows(doc),
            )
          }
        >
          Export Helios pre-staging CSV
        </button>
      </div>

      {records.map((rec) => (
        <div key={rec.ref} className="hs-panel">
          <div className="hs-head" onClick={() => setOpen(open === rec.ref ? null : rec.ref)}>
            <div className="t">
              {rec.mandated && <span className="star">★ </span>}
              <b>{rec.ref}</b> — {rec.title}
            </div>
            <div>
              <span className={`cbadge ${rec.complete ? "ok" : "no"}`}>
                {rec.complete ? "✓ ready" : `${rec.missing.length} missing`}
              </span>{" "}
              <span className="muted">{open === rec.ref ? "▴" : "▾"}</span>
            </div>
          </div>

          {open === rec.ref && (
            <div className="hs-grid">
              {spec.fields.map((field) => {
                const value = rec.values[field.key] ?? "";
                const options =
                  field.key === "business"
                    ? spec.business
                    : field.key === "location"
                      ? spec.location
                      : field.allowed;

                return (
                  <div
                    key={field.key}
                    className={`hs-f g-${field.group} ${field.full_width ? "full" : ""} ${field.required ? "req" : ""}`}
                    style={field.full_width ? { gridColumn: "1 / -1" } : undefined}
                  >
                    <label>
                      {field.label}
                      {field.hint && <span className="muted"> · {field.hint}</span>}
                    </label>

                    {field.type === "derived" ? (
                      <div className="derived">{value || "—"} <span className="muted small">· auto</span></div>
                    ) : field.key === "location" ? (
                      <div className="derived" style={{ borderStyle: "solid", background: "#f7f9fc" }}>
                        {value || "none"}{" "}
                        <span className="muted small">· set on the Risk Radar tab</span>
                      </div>
                    ) : options ? (
                      <select
                        defaultValue={value}
                        onChange={(e) => save(rec.ref, field.key, e.target.value)}
                      >
                        <option value="">— select —</option>
                        {options.map((o) => (
                          <option key={o}>{o}</option>
                        ))}
                      </select>
                    ) : field.type === "textarea" ? (
                      <textarea
                        defaultValue={value}
                        onBlur={(e) => e.target.value !== value && save(rec.ref, field.key, e.target.value)}
                      />
                    ) : (
                      <input
                        type={field.type === "date" ? "date" : "text"}
                        defaultValue={value}
                        onBlur={(e) => e.target.value !== value && save(rec.ref, field.key, e.target.value)}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
      {records.length === 0 && <p className="muted">No in-plan reviews yet — stage some first.</p>}
    </div>
  );
}

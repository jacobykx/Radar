"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import type { PlanState } from "@/lib/usePlan";

interface Field {
  key: string;
  label: string;
  type: string;
  group: string;
  allowed: string[] | null;
  hint: string | null;
  full_width: boolean;
  required: boolean;
}
interface Spec {
  fields: Field[];
  business: string[];
  location: string[];
}
interface Record_ {
  ref: string;
  title: string;
  mandated: boolean;
  target_start: string | null;
  values: Record<string, string>;
  complete: boolean;
  missing: string[];
}

/**
 * Helios pre-staging.
 *
 * The field set is fetched from the backend rather than duplicated here — the Planning
 * Key Fields spec is owned by Helios, so a spec change should not need a UI release.
 */
export function Prestaging({ plan }: { plan: PlanState }) {
  const [spec, setSpec] = useState<Spec | null>(null);
  const [records, setRecords] = useState<Record_[]>([]);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [s, list] = await Promise.all([api.GET("/prestaging/spec", {}), api.GET("/prestaging", { params: { query: {} } })]);
    if (s.data) setSpec(s.data as unknown as Spec);
    if (list.data) setRecords(list.data as unknown as Record_[]);
  }, []);

  useEffect(() => {
    load();
  }, [load, plan.reviews]);

  const save = async (ref: string, key: string, value: string) => {
    await api.PATCH("/prestaging/{ref}", {
      params: { path: { ref } },
      body: { changes: { [key]: value } },
    });
    await load();
  };

  if (!spec) return <div className="panel muted">Loading the Helios field spec…</div>;

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
        <a className="btn primary" href={`${process.env.NEXT_PUBLIC_API_BASE}/prestaging/export`}>
          Export Helios pre-staging CSV
        </a>
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

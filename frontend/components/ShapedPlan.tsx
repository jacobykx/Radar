"use client";

import { Fragment, useMemo, useState } from "react";

import { csv, QUARTERS, select } from "@/lib/engine";
import type { PlanState } from "@/lib/usePlan";

/** The shaped plan: a quarter Gantt grouped by assurance function. */
export function ShapedPlan({ plan }: { plan: PlanState }) {
  const { doc } = plan;
  const [team, setTeam] = useState("");

  const groups = useMemo(() => (doc ? select.shapedPlan(doc).groups : []), [doc]);
  const shown = groups.filter((g) => !team || g.function === team);

  return (
    <div className="panel">
      <h3>
        Shaped indicative plan{" "}
        <span className="sub">— in-plan reviews by assurance function, for 1LOD interlock and L2.</span>
      </h3>
      <div className="rowactions">
        <label>
          Assurance function
          <select value={team} onChange={(e) => setTeam(e.target.value)}>
            <option value="">All functions</option>
            {groups.map((g) => (
              <option key={g.function}>{g.function}</option>
            ))}
          </select>
        </label>
        <button
          className="btn primary"
          disabled={!doc}
          onClick={() =>
            doc && csv.downloadCsv(`${doc.plan.year}_IAP_shaped_plan.csv`, csv.planRows(doc))
          }
        >
          Export plan to CSV
        </button>
      </div>

      <div className="scroll">
        <table className="gantt">
          <thead>
            <tr>
              <th className="lbl">Review / function</th>
              {QUARTERS.map((q) => (
                <th key={q} style={{ textAlign: "center", width: 150 }}>
                  {q}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((g) => (
              <Fragment key={g.function}>
                <tr className="gteam">
                  <td>
                    {g.function} <span className="muted">· {g.total_fte} FTE</span>
                  </td>
                  {QUARTERS.map((q) => (
                    <td key={q} className="qcell">
                      {g.by_quarter[q] || ""}
                    </td>
                  ))}
                </tr>
                {g.reviews.map((r) => (
                  <tr key={r.ref}>
                    <td>
                      <div>
                        {r.mandated && <span className="star">★ </span>}
                        <b>{r.ref}</b> {r.title}
                      </div>
                      <div className="glbl sme">
                        {r.size} · {r.fte} FTE ·{" "}
                        {[r.business, r.locations.join(", ")].filter(Boolean).join(" · ") ||
                          "business / location TBC"}
                        {!r.quarter && <span style={{ color: "var(--over)" }}> · quarter TBC</span>}
                      </div>
                    </td>
                    {QUARTERS.map((q) => (
                      <td key={q} className="qcell">
                        {r.quarter === q && (
                          <div className={`gbar ${r.mandated ? "Mandated" : r.band}`} title={`${r.title} — ${q}`}>
                            {r.ref} · {r.fte} FTE
                          </div>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </Fragment>
            ))}
            {shown.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  Nothing staged yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import { api, type Review } from "@/lib/api/client";
import type { PlanState } from "@/lib/usePlan";

import { RationaleBox } from "./RiskRadar";

interface Dashboard {
  total: number;
  by_status: Record<string, number>;
  approved_pct: number;
  by_origin: Record<string, number>;
  by_route: Record<string, { total: number; approved: number }>;
  linkage: Record<string, string[]>;
}

/** Approval: filters, per-review sign-off, bulk approve, and filter-reactive dashboards. */
export function Approval({ plan }: { plan: PlanState }) {
  const { act, refresh } = plan;
  const [rows, setRows] = useState<Review[]>([]);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [f, setF] = useState({ team: "", business: "", location: "", route: "", status: "" });

  const query = Object.fromEntries(Object.entries(f).filter(([, v]) => v)) as Record<string, string>;

  const load = useCallback(async () => {
    const r = await api.GET("/approvals", { params: { query } });
    if (r.data) {
      const d = r.data as unknown as { reviews: Review[]; dashboard: Dashboard };
      setRows(d.reviews);
      setDash(d.dashboard);
    }
  }, [JSON.stringify(query)]);

  useEffect(() => {
    load();
  }, [load, plan.reviews]);

  const teams = [...new Set(plan.reviews.map((r) => r.assurance_function))].sort();
  const businesses = [...new Set(plan.reviews.map((r) => r.business).filter(Boolean))].sort() as string[];
  const locations = [...new Set(plan.reviews.flatMap((r) => r.locations))].sort();

  const decide = async (ref: string, decision: "Approved" | "Returned", comment?: string) => {
    const ok = await act(() =>
      api.POST("/reviews/{ref}/approval", {
        params: { path: { ref } },
        body: { decision, comment: comment ?? null },
      }),
    );
    if (ok) await load();
    return ok;
  };

  return (
    <div className="panel">
      <h3>
        Approval{" "}
        <span className="sub">
          — the staged plan for 1LOD interlock and L2 sign-off. One gate per review, routed by type.
        </span>
      </h3>

      <div className="rowactions">
        {(
          [
            ["team", "Team", teams],
            ["business", "Business", businesses],
            ["location", "Location", locations],
            ["route", "Route", ["IRR", "RCA", "Standard"]],
            ["status", "Status", ["Pending", "Approved", "Returned"]],
          ] as const
        ).map(([key, label, options]) => (
          <label key={key}>
            {label}
            <select value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })}>
              <option value="">All</option>
              {options.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </label>
        ))}
        <button
          className="btn up"
          onClick={async () => {
            await api.POST("/approvals/bulk-approve", { body: query });
            await refresh();
            await load();
          }}
        >
          ✓ Approve all in view
        </button>
        <a
          className="btn primary"
          href={`${process.env.NEXT_PUBLIC_API_BASE}/approvals/export?${new URLSearchParams(query)}`}
        >
          Export view to CSV
        </a>
      </div>

      {dash && (
        <div className="dashwrap" style={{ marginBottom: 12 }}>
          <div className="dashcard">
            <div className="dashttl">Sign-off status · {dash.total} reviews</div>
            <div className="funnel">
              {["Pending", "Approved", "Returned"].map((s) => (
                <div className="fstep" key={s}>
                  <div className="fn">{dash.by_status[s] ?? 0}</div>
                  <div className="fl">{s}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="dashcard">
            <div className="dashttl">Approved</div>
            <div className="donut" style={{ ["--pct" as string]: dash.approved_pct }}>
              <span>{dash.approved_pct}%</span>
            </div>
          </div>
          <div className="dashcard">
            <div className="dashttl">By origin</div>
            <div className="attn">
              {Object.entries(dash.by_origin).map(([o, n]) => (
                <div key={o} className="ai">
                  <b>{n}</b> <span className={`origin ${originClass(o)}`}>{o}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="dashcard">
            <div className="dashttl">By route</div>
            <div className="attn">
              {Object.entries(dash.by_route).map(([r, v]) => (
                <div key={r} className={`ai ${v.total && v.approved === v.total ? "good" : v.total ? "bad" : ""}`}>
                  <b>
                    {v.approved}/{v.total}
                  </b>{" "}
                  {r === "IRR" ? "IRR · mandated" : r === "RCA" ? "RCA-linked" : "Standard"}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Ref</th>
              <th>Review</th>
              <th>Origin</th>
              <th>Regulatory ref</th>
              <th>Team</th>
              <th>Business</th>
              <th>Location</th>
              <th>Qtr</th>
              <th>Size</th>
              <th className="num">FTE</th>
              <th>Approval</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.ref}>
                <tr>
                  <td>
                    {r.mandated && <span className="star">★ </span>}
                    {r.ref}
                  </td>
                  <td>
                    <b>{r.title}</b>
                    <div className="muted small">
                      {r.route === "IRR"
                        ? "IRR · regulator-mandated"
                        : r.route === "RCA"
                          ? "RCA-linked"
                          : "Standard route"}
                    </div>
                  </td>
                  <td><span className={`origin ${originClass(r.origin)}`}>{r.origin}</span></td>
                  <td className="small regref">
                    {r.route === "IRR" ? (
                      <>
                        {r.rris_ids.length > 0 ? (
                          r.rris_ids.map((i) => (
                            <span key={i} className="rris">
                              {i}
                            </span>
                          ))
                        ) : (
                          <span className="flagchip">no RRIS ID</span>
                        )}
                        <div className="muted" style={{ fontSize: 11 }}>
                          {r.regulator} {r.regulation && `· ${r.regulation}`}
                        </div>
                        {(dash?.linkage[r.ref]?.length ?? 0) > 0 && (
                          <div className="linkchip" title={dash!.linkage[r.ref].join(", ")}>
                            ⇄ also in {dash!.linkage[r.ref].length} other review(s)
                          </div>
                        )}
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="small">{r.assurance_function.replace(" Assurance", "")}</td>
                  <td className="small">{r.business ?? "—"}</td>
                  <td className="small">{r.locations.join(", ") || "—"}</td>
                  <td className="small">{r.planned_quarter ?? "—"}</td>
                  <td className="small">{r.effort_size}</td>
                  <td className="num">{r.fte}</td>
                  <td>
                    <span className={`appr ${apprClass(r.approval_status)}`}>{r.approval_status}</span>
                  </td>
                  <td>
                    <button
                      className="btn sm"
                      onClick={() => {
                        const next = new Set(open);
                        next.has(r.ref) ? next.delete(r.ref) : next.add(r.ref);
                        setOpen(next);
                      }}
                    >
                      {open.has(r.ref) ? "▴" : "▾"} Sign-off
                    </button>
                  </td>
                </tr>
                {open.has(r.ref) && (
                  <tr className="detail">
                    <td colSpan={12}>
                      <div className="box">
                        <h5>Sign-off gate</h5>
                        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                          <button className="btn sm up" onClick={() => decide(r.ref, "Approved")}>
                            Approve
                          </button>
                        </div>
                        <RationaleBox
                          label="Return this review"
                          placeholder="Comment (required to return)"
                          confirmLabel="Return"
                          hint="Approving needs no words; returning does."
                          onConfirm={(text) => decide(r.ref, "Returned", text)}
                        />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={12} className="muted">
                  No in-plan reviews match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function apprClass(status: string) {
  if (status === "Approved") return "ap-ok";
  if (status === "Returned") return "ap-ret";
  return "ap-pend";
}

function originClass(origin: string) {
  if (origin === "Regulatory Assurance") return "o-reg";
  if (origin === "Risk Assurance") return "o-risk";
  return "o-radar";
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { api, QUARTERS, type Quarter, type Review } from "@/lib/api/client";
import type { PlanState } from "@/lib/usePlan";

interface Capacity {
  scope: {
    label: string;
    candidate_reviews: number;
    fte_per_quarter: number;
    annual_fte_quarters: number;
  };
  bottom_up: {
    annual_fte_quarters: number;
    mandated_fte: number;
    additional_fte: number;
    remaining_after_mandated: number;
    headroom: number;
    over: boolean;
  };
  aggregate: { quarter: string; capacity: number; demand: number; over: boolean; warn: boolean }[];
  unscheduled_count: number;
}

type SortKey = "default" | "staged" | "ref" | "origin" | "eff" | "effort" | "quarter";

/**
 * Staging & capacity — matched to the prototype's four panels: the team view and its
 * actions, the bottom-up fill bar, quarterly demand against capacity, then the
 * scheduling table.
 *
 * The capacity figures shown here are the roll-up across the teams in scope, as the
 * prototype does. Scheduling itself is enforced per assurance function on the server —
 * one function's spare FTE never covers another's.
 */
export function StagingCapacity({ plan }: { plan: PlanState }) {
  const { reviews, act, refresh } = plan;
  const [capacity, setCapacity] = useState<Capacity | null>(null);
  const [team, setTeam] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("default");
  const [sortDir, setSortDir] = useState(1);

  const loadCapacity = useCallback(async () => {
    const r = await api.GET("/capacity", { params: { query: team ? { team } : {} } });
    if (r.data) setCapacity(r.data as unknown as Capacity);
  }, [team]);

  useEffect(() => {
    loadCapacity();
  }, [loadCapacity, reviews]);

  const teams = [...new Set(reviews.map((r) => r.assurance_function))].sort();
  const scope = reviews.filter((r) => !r.descoped && (!team || r.assurance_function === team));

  const autofill = async () => {
    const r = await api.POST("/plan/autofill", {});
    if (r.data) {
      const d = r.data as { summary: string; unplaced: { ref: string }[] };
      setResult(
        d.unplaced.length > 0
          ? `${d.summary}. Could not fit: ${d.unplaced.map((u) => u.ref).join(", ")} — descope, resize or add capacity.`
          : d.summary,
      );
    }
    await refresh();
    await loadCapacity();
  };

  const rows = [...scope].sort((a, b) => {
    if (sortKey === "default") {
      return Number(b.staged) - Number(a.staged) || (b.effective_priority ?? 0) - (a.effective_priority ?? 0);
    }
    if (sortKey === "ref") return a.ref.localeCompare(b.ref, undefined, { numeric: true }) * sortDir;
    if (sortKey === "origin") return a.origin.localeCompare(b.origin) * sortDir;
    const value = (r: Review) =>
      sortKey === "staged"
        ? Number(r.staged)
        : sortKey === "eff"
          ? (r.effective_priority ?? 0)
          : sortKey === "effort"
            ? r.effort_days
            : QUARTERS.indexOf((r.planned_quarter ?? "") as Quarter) < 0
              ? 99
              : QUARTERS.indexOf(r.planned_quarter as Quarter);
    return (value(a) - value(b)) * sortDir || a.ref.localeCompare(b.ref, undefined, { numeric: true });
  });

  const sortHead = (key: SortKey, label: string) => (
    <th
      className="sortable"
      onClick={() => {
        if (key === sortKey) setSortDir(-sortDir);
        else {
          setSortKey(key);
          setSortDir(1);
        }
      }}
    >
      {label}
      <span className="arr">{sortKey === key ? (sortDir < 0 ? " ▼" : " ▲") : ""}</span>
    </th>
  );

  const bu = capacity?.bottom_up;
  const annual = bu?.annual_fte_quarters || 1;
  const mandPct = bu ? Math.min(100, (bu.mandated_fte / annual) * 100) : 0;
  const addPct = bu ? Math.max(0, Math.min(100 - mandPct, (bu.additional_fte / annual) * 100)) : 0;

  return (
    <>
      <div className="panel">
        <h3>
          Assurance team view{" "}
          <span className="sub">
            — each assurance team stages &amp; schedules its own reviews against its own capacity.
          </span>
        </h3>
        <div className="rowactions" style={{ marginBottom: 0 }}>
          <label>
            Team{" "}
            <select className="teamsel" value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">All teams</option>
              {teams.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <button className="btn" onClick={autofill}>
            Auto-fill quarters (waterfall Q1→Q4)
          </button>
          <button
            className="btn ghost"
            onClick={async () => {
              await api.POST("/plan/clear-quarters", {});
              setResult(null);
              await refresh();
              await loadCapacity();
            }}
          >
            Clear quarters
          </button>
          {capacity && (
            <span className="muted small">
              {capacity.scope.label}: {capacity.scope.candidate_reviews} candidate reviews ·{" "}
              {capacity.scope.fte_per_quarter} FTE per quarter (
              {capacity.scope.annual_fte_quarters} FTE-quarters/yr).
            </span>
          )}
        </div>
        {result && (
          <div className="banner ok" style={{ marginTop: 12, marginBottom: 0 }}>
            {result}
          </div>
        )}
      </div>

      {bu && (
        <div className="panel">
          <h3>
            Bottom-up capacity fill{" "}
            <span className="sub">
              — mandated reviews (★) commit capacity first; the rest fill what remains. Sizes carry
              an FTE requirement: S = 2 · M = 3 · L = 4.
            </span>
          </h3>
          <div className="bu-bar">
            <span className="seg mand" style={{ width: `${mandPct}%` }} />
            <span className="seg add" style={{ width: `${addPct}%` }} />
          </div>
          <div className="bu-legend">
            <span>
              <i className="sw" style={{ background: "var(--partial)" }} />
              Mandated committed: <b>{bu.mandated_fte} FTE</b>
            </span>
            <span>
              <i className="sw" style={{ background: "var(--blue)" }} />
              Additional allocated: <b>{bu.additional_fte} FTE</b>
            </span>
            <span>
              Remaining after mandated: <b>{bu.remaining_after_mandated} FTE</b>
            </span>
            <span className={bu.over ? "over" : ""}>
              Free headroom: <b>{bu.headroom} FTE</b>
            </span>
            <span>
              Annual capacity: <b>{bu.annual_fte_quarters} FTE-quarters</b>
            </span>
          </div>
          {bu.over ? (
            <div className="gapflag" style={{ marginTop: 8, marginBottom: 0 }}>
              ⚠ Staged demand exceeds annual FTE capacity by <b>{-bu.headroom} FTE</b> — descope,
              resize or add capacity.
            </div>
          ) : (
            <div className="gapflag none" style={{ marginTop: 8, marginBottom: 0 }}>
              ✓ Mandated committed; {bu.headroom} FTE-quarters remain for further reviews.
            </div>
          )}
        </div>
      )}

      {capacity && (
        <div className="panel">
          <h3>
            Quarterly FTE demand vs capacity{" "}
            <span className="sub">
              — reviews scheduled in a quarter draw their FTE concurrently; team capacity = its
              headcount.
            </span>
          </h3>
          {capacity.aggregate.map((q) => (
            <div className="cap-row" key={q.quarter}>
              <div className="name">{q.quarter}</div>
              <div className={`bar ${q.over ? "over" : q.warn ? "warn" : ""}`}>
                <span
                  style={{ width: `${q.capacity ? Math.min(100, (q.demand / q.capacity) * 100) : 0}%` }}
                />
              </div>
              <div className={`cap-num ${q.over ? "over" : ""}`}>
                <b>{q.demand}</b> / {q.capacity} FTE
              </div>
            </div>
          ))}
          {capacity.unscheduled_count > 0 ? (
            <div className="gapflag" style={{ marginTop: 8, marginBottom: 0 }}>
              {capacity.unscheduled_count} staged review
              {capacity.unscheduled_count > 1 ? "s" : ""} not yet scheduled — use{" "}
              <b>Auto-fill quarters</b> to waterfall them Q1→Q4.
            </div>
          ) : (
            <div className="gapflag none" style={{ marginTop: 8, marginBottom: 0 }}>
              ✓ All staged reviews are scheduled to a quarter.
            </div>
          )}
        </div>
      )}

      <div className="panel flush">
        <table>
          <thead>
            <tr>
              {sortHead("staged", "Stage")}
              <th>★</th>
              {sortHead("ref", "Ref")}
              <th>Candidate review</th>
              {sortHead("origin", "Origin")}
              {sortHead("eff", "Priority")}
              {sortHead("effort", "Size")}
              <th>FTE</th>
              {sortHead("quarter", "Planned quarter")}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ref}>
                <td>
                  <input
                    type="checkbox"
                    checked={r.staged}
                    readOnly
                    aria-label={`${r.ref} staged`}
                    title="Stage or descope on the Risk Radar tab — descoping requires a rationale"
                  />
                </td>
                <td>{r.mandated && <span className="star">★</span>}</td>
                <td className="composite">{r.ref}</td>
                <td>{r.title}</td>
                <td>
                  <span className={`origin ${originClass(r.origin)}`}>{r.origin}</span>
                </td>
                <td className="composite">
                  {r.mandated ? <span className="muted">—</span> : r.effective_priority?.toFixed(2)}
                </td>
                <td>
                  <select
                    className="effsel"
                    value={r.effort_size}
                    aria-label={`Size for ${r.ref}`}
                    onChange={(e) =>
                      act(() =>
                        api.PATCH("/reviews/{ref}", {
                          params: { path: { ref: r.ref } },
                          body: { effort_size: e.target.value as "S" | "M" | "L" },
                        }),
                      )
                    }
                  >
                    <option value="S">S · 60d</option>
                    <option value="M">M · 90d</option>
                    <option value="L">L · 120d</option>
                  </select>
                </td>
                <td>
                  <select
                    className={`ftesel ${r.fte_override !== null ? "ovr" : ""}`}
                    value={r.fte}
                    aria-label={`FTE for ${r.ref}`}
                    title={
                      r.fte_override !== null
                        ? `Overridden — the default for ${r.effort_size} is ${defaultFte(r.effort_size)}`
                        : "FTE required"
                    }
                    onChange={(e) =>
                      act(() =>
                        api.PATCH("/reviews/{ref}", {
                          params: { path: { ref: r.ref } },
                          body: { fte_override: Number(e.target.value) },
                        }),
                      )
                    }
                  >
                    {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => (
                      <option key={n} value={n}>
                        {n} FTE
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={r.planned_quarter ?? ""}
                    disabled={!r.staged}
                    aria-label={`Quarter for ${r.ref}`}
                    onChange={(e) =>
                      act(() =>
                        api.PATCH("/reviews/{ref}/quarter", {
                          params: { path: { ref: r.ref } },
                          body: { quarter: (e.target.value || null) as Quarter | null },
                        }),
                      )
                    }
                  >
                    <option value="">—</option>
                    {QUARTERS.map((q) => (
                      <option key={q}>{q}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="muted">
                  No candidate reviews for this team.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function defaultFte(size: string) {
  return size === "S" ? 2 : size === "M" ? 3 : 4;
}

function originClass(origin: string) {
  if (origin === "Regulatory Assurance") return "o-reg";
  if (origin === "Risk Assurance") return "o-risk";
  return "o-radar";
}

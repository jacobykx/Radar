"use client";

import { useMemo, useState } from "react";

import { workflow, type EffortSize, type Review } from "@/lib/engine";
import type { PlanState } from "@/lib/usePlan";

type SortKey = "risk" | "urgency" | "coverage_gap" | "change" | "effective_priority" | "effort_days";

/** Factor scores live under `scores`; priority and effort are top-level. */
function sortValue(review: Review, key: SortKey): number {
  if (key === "effective_priority") return review.effective_priority ?? 0;
  if (key === "effort_days") return review.effort_days;
  return review.scores?.[key] ?? 0;
}

/**
 * Risk Radar.
 *
 * Factor scores render as read-only facts -- there is no control to edit them, and the
 * API would refuse anyway. Priority is editable, but confirming an override needs a
 * rationale, captured inline in the drawer rather than in a browser dialog.
 */
export function RiskRadar({ plan }: { plan: PlanState }) {
  const { reviews, weights } = plan;
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<SortKey>("effective_priority");
  const [sortDir, setSortDir] = useState(-1);
  const [team, setTeam] = useState("");
  const [business, setBusiness] = useState("");
  const [location, setLocation] = useState("");

  const teams = useMemo(
    () => [...new Set(reviews.map((r) => r.assurance_function))].sort(),
    [reviews],
  );
  const businesses = useMemo(
    () => [...new Set(reviews.map((r) => r.business).filter(Boolean))].sort() as string[],
    [reviews],
  );
  const locations = useMemo(
    () => [...new Set(reviews.flatMap((r) => r.locations))].sort(),
    [reviews],
  );

  const rows = useMemo(() => {
    const filtered = reviews.filter(
      (r) =>
        (!team || r.assurance_function === team) &&
        (!business || r.business === business) &&
        // Rule 13: a review may span markets; one matching location is enough.
        (!location || r.locations.includes(location)),
    );
    return [...filtered].sort((a, b) => {
      if (a.mandated !== b.mandated) return a.mandated ? -1 : 1; // mandated pinned to top
      return (sortValue(a, sortKey) - sortValue(b, sortKey)) * sortDir;
    });
  }, [reviews, team, business, location, sortKey, sortDir]);

  const toggle = (ref: string) => {
    const next = new Set(open);
    next.has(ref) ? next.delete(ref) : next.add(ref);
    setOpen(next);
  };

  const sortBy = (key: SortKey) => {
    if (key === sortKey) setSortDir(-sortDir);
    else {
      setSortKey(key);
      setSortDir(-1);
    }
  };

  const head = (key: SortKey, label: string) => (
    <th className="sortable num" onClick={() => sortBy(key)}>
      {label}
      {sortKey === key ? (sortDir < 0 ? " ▼" : " ▲") : ""}
    </th>
  );

  return (
    <>
      {weights && <WeightPanel plan={plan} />}

      <div className="panel">
        <div className="rowactions">
          <label>
            Team
            <select value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">All teams</option>
              {teams.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            Business
            <select value={business} onChange={(e) => setBusiness(e.target.value)}>
              <option value="">All businesses</option>
              {businesses.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </label>
          <label>
            Location
            <select value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">All locations</option>
              {locations.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
          <span className="muted small">
            ★ mandated reviews are pinned and not driver-scored. Scores come from the scoring
            engine and are read-only.
          </span>
        </div>

        <div className="scroll">
          <table className="radar">
            <thead>
              <tr>
                <th>Stage</th>
                <th />
                <th>Ref</th>
                <th>Candidate review</th>
                <th>Risk taxonomy</th>
                {head("risk", "Risk")}
                {head("urgency", "Urgency")}
                {head("coverage_gap", "Coverage")}
                {head("change", "Change")}
                {head("effective_priority", "Priority")}
                <th>Origin</th>
                <th>Team</th>
                <th>Business</th>
                <th>Location</th>
                {head("effort_days", "Effort")}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <RadarRow
                  key={r.ref}
                  review={r}
                  plan={plan}
                  open={open.has(r.ref)}
                  onToggle={() => toggle(r.ref)}
                />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={15} className="muted">
                    No reviews match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function RadarRow({
  review: r,
  plan,
  open,
  onToggle,
}: {
  review: Review;
  plan: PlanState;
  open: boolean;
  onToggle: () => void;
}) {
  const { run } = plan;
  const [pending, setPending] = useState<number | null>(null);

  const priority = r.effective_priority;

  return (
    <>
      <tr className={r.descoped ? "descoped" : ""}>
        <td>
          <input
            type="checkbox"
            checked={r.staged}
            aria-label={`Stage ${r.ref}`}
            onChange={(e) => {
              if (e.target.checked) {
                run((doc) => workflow.setStaged(doc, { ref: r.ref, staged: true }));
              } else {
                // Rule 6: descoping needs a rationale, so open the drawer rather than
                // un-staging on the spot. The API refuses it either way.
                if (!open) onToggle();
              }
            }}
          />
        </td>
        <td>
          <button className="btn sm" onClick={onToggle} title="Notes, descope & rationale">
            {open ? "▴" : "▾"}
          </button>
        </td>
        <td>
          {r.mandated && <span className="star">★ </span>}
          {r.ref}
        </td>
        <td>
          {r.title}
          {r.rationale_outstanding && (
            <span className="flagchip" style={{ marginLeft: 6 }}>
              rationale required
            </span>
          )}
          {r.descoped && (
            <span className="descope-tag" style={{ marginLeft: 6 }}>
              descoped
            </span>
          )}
        </td>
        <td><span className="dom-pill">{r.taxonomy_label}</span></td>
        {r.mandated ? (
          <td className="num muted" colSpan={4} style={{ textAlign: "center" }}>
            — not driver-scored —
          </td>
        ) : (
          <>
            <ScoreCell value={r.scores?.risk} />
            <ScoreCell value={r.scores?.urgency} />
            <ScoreCell value={r.scores?.coverage_gap} />
            <ScoreCell value={r.scores?.change} />
          </>
        )}
        <td className="num">
          {r.mandated ? (
            <span className="band Mandated">Mandated</span>
          ) : (
            <>
              <input
                className={`prioin ${r.priority_override !== null ? "ovr" : ""}`}
                type="number"
                step="0.1"
                min="0"
                max="5"
                value={pending ?? priority?.toFixed(2) ?? ""}
                aria-label={`Priority for ${r.ref}`}
                onChange={(e) => setPending(Number(e.target.value))}
                onBlur={() => {
                  if (pending !== null && Math.abs(pending - (priority ?? 0)) > 0.005 && !open) {
                    onToggle();
                  }
                }}
              />
              <div>
                <span className={`band ${r.band}`}>{r.band}</span>
              </div>
            </>
          )}
        </td>
        <td>
          <span className={`origin ${originClass(r.origin)}`}>{r.origin}</span>
          {r.origin === "Risk Radar inputs" && (
            <div className="small" style={{ marginTop: 3 }}>
              {r.steward ? (
                <span className="stew ok">✓ {r.steward.steward_name}</span>
              ) : (
                <span className="stew no">steward?</span>
              )}
            </div>
          )}
        </td>
        <td className="small">
          {r.assurance_function.replace(" Assurance", "")}
          {r.sub_team && <div className="muted">{r.sub_team}</div>}
        </td>
        <td className="small">{r.business ?? "—"}</td>
        <td className="small">{r.locations.join(", ") || "—"}</td>
        <td className="small">
          <select
            value={r.effort_size}
            aria-label={`Effort size for ${r.ref}`}
            onChange={(e) =>
              run((doc) =>
                workflow.setEffortSize(doc, { ref: r.ref, size: e.target.value as EffortSize }),
              )
            }
          >
            <option value="S">S · 60d</option>
            <option value="M">M · 90d</option>
            <option value="L">L · 120d</option>
          </select>
        </td>
      </tr>

      {open && (
        <tr className="detail">
          <td colSpan={15}>
            <div className="dwrap">
              {!r.mandated && (
                <div className="box">
                  <h5>
                    Priority — computed {r.computed_priority?.toFixed(2)}
                    {r.priority_override !== null && ` · overridden to ${r.priority_override.toFixed(2)}`}
                  </h5>
                  {pending !== null && Math.abs(pending - (priority ?? 0)) > 0.005 ? (
                    <RationaleBox
                      label={`Confirm override to ${pending.toFixed(2)}`}
                      placeholder="Rationale for the override (required)"
                      confirmLabel="Confirm override"
                      onConfirm={(text) => {
                        const { ok } = run((doc) =>
                          workflow.setPriorityOverride(doc, {
                            ref: r.ref,
                            value: pending,
                            rationale: text,
                            row_version: r.row_version,
                          }),
                        );
                        if (ok) setPending(null);
                        return ok;
                      }}
                      onCancel={() => setPending(null)}
                    />
                  ) : (
                    <>
                      <p className="muted small" style={{ margin: 0 }}>
                        Priority is computed from the weighted factor scores. Edit the value in
                        the Priority column to override it — a rationale is required.
                      </p>
                      {r.priority_override !== null && (
                        <>
                          <p className="small" style={{ marginBottom: 6 }}>
                            <b>Rationale:</b> {r.priority_override_rationale}
                          </p>
                          <button
                            className="btn sm"
                            onClick={() =>
                              run((doc) => workflow.clearPriorityOverride(doc, { ref: r.ref }))
                            }
                          >
                            Reset to computed
                          </button>
                        </>
                      )}
                    </>
                  )}
                </div>
              )}

              <div className="box">
                <h5>Scope decision</h5>
                {r.staged ? (
                  <RationaleBox
                    label="Descope this review"
                    placeholder="Reason for descoping (required)"
                    confirmLabel="Confirm descope"
                    hint="It will stop flowing to staging, capacity, approval, pre-staging and the plan."
                    onConfirm={(text) =>
                      run((doc) =>
                        workflow.setStaged(doc, {
                          ref: r.ref,
                          staged: false,
                          rationale: text,
                          row_version: r.row_version,
                        }),
                      ).ok
                    }
                  />
                ) : (
                  <>
                    {r.descope_rationale ? (
                      <p className="small">
                        <b>Descoped:</b> {r.descope_rationale}
                      </p>
                    ) : (
                      <p className="warn-inline" style={{ marginLeft: 0 }}>No rationale on record for this review.</p>
                    )}
                    <button
                      className="btn sm up"
                      onClick={() =>
                        run((doc) => workflow.setStaged(doc, { ref: r.ref, staged: true }))
                      }
                    >
                      Bring back into scope
                    </button>
                  </>
                )}
              </div>

              {r.origin === "Risk Radar inputs" && (
                <div className="box">
                  <h5>Risk steward consultation</h5>
                  {r.steward ? (
                    <p className="small">
                      <span className="ok">✓ Consulted</span> — <b>{r.steward.steward_name}</b>,
                      recorded by {r.steward.recorded_by}
                    </p>
                  ) : (
                    <RationaleBox
                      label=""
                      placeholder="Risk steward name (required)"
                      confirmLabel="Confirm consulted"
                      single
                      hint="Stewards are consulted before the plan is shaped, so their requirements are reflected rather than raised at quarter-end."
                      onConfirm={(text) =>
                        run((doc) => workflow.recordSteward(doc, { ref: r.ref, steward_name: text }))
                          .ok
                      }
                    />
                  )}
                </div>
              )}

              {(r.regulator || r.regulation || r.rris_ids.length > 0) && (
                <div className="box">
                  <h5>Regulatory detail</h5>
                  <p className="small" style={{ margin: 0 }}>
                    {r.regulator && (
                      <>
                        <b>Regulator:</b> {r.regulator}
                        <br />
                      </>
                    )}
                    {r.regulation && (
                      <>
                        <b>Regulation:</b> {r.regulation}
                        <br />
                      </>
                    )}
                    {r.rris_ids.length > 0 && (
                      <>
                        <b>RRIS:</b> {r.rris_ids.join(", ")}
                      </>
                    )}
                  </p>
                </div>
              )}

              <div className="box" style={{ gridColumn: "1 / -1" }}>
                <h5>Notes &amp; decision log</h5>
                <RationaleBox
                  label=""
                  placeholder="Add a note / rationale…"
                  confirmLabel="Add note"
                  onConfirm={(text) => run((doc) => workflow.addNote(doc, { ref: r.ref, text })).ok}
                />
                {(r.notes ?? []).length === 0 ? (
                  <p className="muted small">No notes yet.</p>
                ) : (
                  (r.notes ?? []).map((n, i) => (
                    <p key={i} className="small" style={{ margin: "4px 0" }}>
                      <span className="muted">
                        {n.author} · {new Date(n.created_at).toLocaleString()} —{" "}
                      </span>
                      {n.text}
                    </p>
                  ))
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function ScoreCell({ value }: { value: number | undefined }) {
  return (
    <td className="num">
      <span className={`sc s${Math.round(value ?? 0)}`} title="From the scoring engine — read-only fact">
        {value ?? "—"}
      </span>
    </td>
  );
}

/** Inline rationale capture. Never a browser dialog — the brief forbids it. */
export function RationaleBox({
  label,
  placeholder,
  confirmLabel,
  hint,
  single,
  onConfirm,
  onCancel,
}: {
  label: string;
  placeholder: string;
  confirmLabel: string;
  hint?: string;
  single?: boolean;
  onConfirm: (text: string) => Promise<boolean> | boolean;
  onCancel?: () => void;
}) {
  const [text, setText] = useState("");
  const [warn, setWarn] = useState(false);

  return (
    <div>
      {label && <p className="small" style={{ margin: "0 0 4px", fontWeight: 600 }}>{label}</p>}
      {hint && <p className="muted small" style={{ margin: "0 0 6px" }}>{hint}</p>}
      {single ? (
        <input
          style={{ width: "100%" }}
          placeholder={placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      ) : (
        <textarea placeholder={placeholder} value={text} onChange={(e) => setText(e.target.value)} />
      )}
      <div style={{ marginTop: 6, display: "flex", gap: 6, alignItems: "center" }}>
        <button
          className="btn sm primary"
          onClick={async () => {
            if (!text.trim()) {
              setWarn(true);
              return;
            }
            const ok = await onConfirm(text.trim());
            if (ok !== false) setText("");
          }}
        >
          {confirmLabel}
        </button>
        {onCancel && (
          <button className="btn sm" onClick={onCancel}>
            Cancel
          </button>
        )}
        {warn && !text.trim() && <span className="warn-inline">A rationale is required.</span>}
      </div>
    </div>
  );
}

function WeightPanel({ plan }: { plan: PlanState }) {
  const { weights, run } = plan;
  const [local, setLocal] = useState(weights);

  if (!weights || !local) return null;

  const fields: [keyof typeof local, string][] = [
    ["risk", "Risk score"],
    ["urgency", "Urgency index"],
    ["coverage_gap", "Coverage gap"],
    ["change", "Change index"],
  ];

  return (
    <details className="help">
      <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
        ⚖ Priority weights{" "}
        <span className="muted small" style={{ fontWeight: 400 }}>
          — scores are read-only facts; weights set what matters most
        </span>
      </summary>
      <div className="weights" style={{ marginTop: 4 }}>
        {fields.map(([key, label]) => (
          <div className="wt" key={key}>
            <label>
              <b>{label}</b> · weight <span className="val">{local[key].toFixed(1)}</span>
            </label>
            <input
              type="range"
              min={0}
              max={3}
              step={0.5}
              value={local[key]}
              aria-label={`${label} weight`}
              onChange={(e) => setLocal({ ...local, [key]: Number(e.target.value) })}
              onMouseUp={() => run((doc) => workflow.setWeights(doc, local))}
              onTouchEnd={() => run((doc) => workflow.setWeights(doc, local))}
            />
          </div>
        ))}
      </div>
      <p className="muted small">
        Priority = (a·risk + b·urgency + c·coverage gap + d·change) ÷ (a+b+c+d), so the result
        stays on the 1–5 scale whatever the weights.
      </p>
    </details>
  );
}

function originClass(origin: string) {
  if (origin === "Regulatory Assurance") return "o-reg";
  if (origin === "Risk Assurance") return "o-risk";
  return "o-radar";
}

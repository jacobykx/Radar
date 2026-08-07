"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import type { PlanState } from "@/lib/usePlan";

interface Version {
  id: number;
  name: string;
  note: string;
  author: string;
  created_at: string;
  staged_count: number;
}
interface AuditRow {
  id: number;
  review_ref: string | null;
  action: string;
  detail: string;
  username: string;
  created_at: string;
}
interface Outstanding {
  ref: string;
  title: string;
  assurance_function: string;
  effective_priority: number | null;
}

/** Versions: snapshot and restore the whole plan state. */
export function Versions({ plan }: { plan: PlanState }) {
  const [versions, setVersions] = useState<Version[]>([]);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState<number | null>(null);

  const load = useCallback(async () => {
    const r = await api.GET("/versions", {});
    if (r.data) setVersions(r.data as unknown as Version[]);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="panel">
      <h3>
        Version control{" "}
        <span className="sub">
          — snapshot staging, quarters, overrides, sizes, pre-staging and sign-off, and restore any
          baseline. The audit trail is never rolled back.
        </span>
      </h3>
      <div className="rowactions">
        <input
          style={{ flex: "1 1 240px" }}
          placeholder="Version name — e.g. Baseline v1 / Post-1LOD interlock"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          style={{ flex: "1 1 200px" }}
          placeholder="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          className="btn primary"
          disabled={!name.trim()}
          onClick={async () => {
            await api.POST("/versions", { body: { name, note } });
            setName("");
            setNote("");
            await load();
          }}
        >
          Save current as version
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Version</th>
            <th>Saved</th>
            <th>By</th>
            <th className="num">Staged</th>
            <th>Note</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <Fragment key={v.id}>
              <tr>
                <td>
                  <b>{v.name}</b>
                </td>
                <td className="small muted">{new Date(v.created_at).toLocaleString()}</td>
                <td className="small">{v.author}</td>
                <td className="num">{v.staged_count}</td>
                <td className="small">{v.note}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn sm" onClick={() => setConfirming(v.id)}>
                    Restore
                  </button>{" "}
                  <button
                    className="btn sm down"
                    onClick={async () => {
                      await api.DELETE("/versions/{version_id}", {
                        params: { path: { version_id: v.id } },
                      });
                      await load();
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
              {confirming === v.id && (
                <tr className="detail">
                  <td colSpan={6}>
                    <b>Restore “{v.name}”?</b> Current unsaved changes will be replaced.{" "}
                    <button
                      className="btn sm primary"
                      onClick={async () => {
                        await api.POST("/versions/{version_id}/restore", {
                          params: { path: { version_id: v.id } },
                        });
                        setConfirming(null);
                        await plan.refresh();
                        await load();
                      }}
                    >
                      Confirm restore
                    </button>{" "}
                    <button className="btn sm" onClick={() => setConfirming(null)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {versions.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No versions saved yet — save the current plan as a baseline.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Audit trail: chronological, append-only, exportable. */
export function AuditTrail({ plan }: { plan: PlanState }) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [outstanding, setOutstanding] = useState<Outstanding[]>([]);

  useEffect(() => {
    api.GET("/audit", { params: { query: {} } }).then((r) => r.data && setRows(r.data as unknown as AuditRow[]));
    api
      .GET("/audit/outstanding", {})
      .then((r) => r.data && setOutstanding(r.data as unknown as Outstanding[]));
  }, [plan.reviews]);

  return (
    <>
      <div className="panel">
        <h3>
          Outstanding rationales{" "}
          <span className="sub">— out of the plan with no rationale on record.</span>
        </h3>
        {outstanding.length === 0 ? (
          <div className="gapflag none">
            ✓ No outstanding rationales — every review out of the plan has a recorded reason.
          </div>
        ) : (
          outstanding.map((o) => (
            <div className="gapflag" key={o.ref}>
              <b>
                {o.ref} — {o.title}
              </b>
              <div className="muted small">
                {o.assurance_function} · priority {o.effective_priority?.toFixed(2) ?? "—"}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="panel">
        <h3>
          Audit trail{" "}
          <span className="sub">
            — every decision, most recent first. Append-only: entries cannot be edited or deleted.
          </span>
        </h3>
        <div className="rowactions">
          <a className="btn primary" href={`${process.env.NEXT_PUBLIC_API_BASE}/audit/export`}>
            Export audit trail to CSV
          </a>
        </div>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Ref</th>
                <th>Action</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td className="small muted" style={{ whiteSpace: "nowrap" }}>
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="small">{a.username}</td>
                  <td className="small">{a.review_ref ?? "—"}</td>
                  <td className="small">
                    <b>{a.action}</b>
                  </td>
                  <td className="small">{a.detail}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    No decisions logged yet.
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

/** Reference data: the admin fallback behind the Helios KBD feed. */
export function ReferenceData({ plan }: { plan: PlanState }) {
  const [data, setData] = useState<Record<string, { code: string; label: string }[]> | null>(null);
  const [impact, setImpact] = useState<Record<string, string[]> | null>(null);
  const [text, setText] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [d, i] = await Promise.all([
      api.GET("/reference-data", {}),
      api.GET("/reference-data/impact", {}),
    ]);
    if (d.data) {
      const payload = d.data as unknown as Record<string, { code: string; label: string }[]>;
      setData(payload);
      setText({
        taxonomy: payload.taxonomy.map((t) => `${t.code} | ${t.label}`).join("\n"),
        business: payload.business.map((t) => t.label).join("\n"),
        location: payload.location.map((t) => t.label).join("\n"),
      });
    }
    if (i.data) setImpact(i.data as unknown as Record<string, string[]>);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!data) return <div className="panel muted">Loading reference data…</div>;

  const parse = (raw: string, withCode: boolean) =>
    raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((line) => {
        if (!withCode) return { code: line, label: line };
        const i = line.indexOf("|");
        return i < 0
          ? { code: line, label: line }
          : { code: line.slice(0, i).trim(), label: line.slice(i + 1).trim() };
      });

  return (
    <>
      <div className="panel">
        <h3>
          Reference data{" "}
          <span className="sub">
            — in production these come from the Helios KBD reference-data mapper; this screen is
            the admin fallback.
          </span>
        </h3>
        <p className="refnote">
          One value per line. For <b>Risk taxonomy L3</b> use <code>code | label</code> — the code
          is stored against each review, so keep existing codes to retain current taxonomy.
          Retired values are deactivated, never deleted, so nothing breaks.
        </p>
        <div className="refgrid">
          {(
            [
              ["taxonomy", "Risk taxonomy L3", true],
              ["business", "Business", false],
              ["location", "Location", false],
            ] as const
          ).map(([key, label]) => (
            <div className="refbox" key={key}>
              <label>
                {label} <span className="muted">({data[key].length})</span>
              </label>
              <textarea
                style={{ minHeight: 200, fontFamily: "ui-monospace, monospace", fontSize: 12 }}
                value={text[key] ?? ""}
                onChange={(e) => setText({ ...text, [key]: e.target.value })}
              />
            </div>
          ))}
        </div>
        <div className="rowactions" style={{ marginTop: 10 }}>
          <button
            className="btn primary"
            onClick={async () => {
              const r = await api.PUT("/reference-data", {
                body: {
                  taxonomy: parse(text.taxonomy ?? "", true),
                  business: parse(text.business ?? "", false),
                  location: parse(text.location ?? "", false),
                },
              });
              setMessage(r.error ? "Rejected — check the values." : "Applied.");
              await load();
              await plan.refresh();
            }}
          >
            Apply reference data
          </button>
          {message && <span className="small" style={{ color: "var(--ok)" }}>{message}</span>}
        </div>
      </div>

      <div className="panel">
        <h3>
          Impact <span className="sub">— values still carried by reviews but no longer listed.</span>
        </h3>
        {impact && Object.values(impact).every((v) => v.length === 0) ? (
          <div className="gapflag none">✓ Every value used by current reviews exists in the lists.</div>
        ) : (
          impact &&
          Object.entries(impact)
            .filter(([, v]) => v.length > 0)
            .map(([k, v]) => (
              <div className="gapflag" key={k}>
                ⚠ {k} values on reviews but not in the list: <b>{v.join(", ")}</b>
              </div>
            ))
        )}
      </div>
    </>
  );
}

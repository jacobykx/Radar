"use client";

import { Fragment, useMemo, useState } from "react";

import { csv, select, workflow, type ReferenceKind } from "@/lib/engine";
import type { PlanState } from "@/lib/usePlan";

/** Versions: snapshot and restore the whole plan state. */
export function Versions({ plan }: { plan: PlanState }) {
  const { doc, run } = plan;
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState<number | null>(null);

  const versions = useMemo(() => (doc ? select.versionRows(doc) : []), [doc]);

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
          onClick={() => {
            const { ok } = run((current) => workflow.saveVersion(current, { name, note }));
            if (ok) {
              setName("");
              setNote("");
            }
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
                    onClick={() => run((current) => workflow.deleteVersion(current, { id: v.id }))}
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
                      onClick={() => {
                        run((current) => workflow.restoreVersion(current, { id: v.id }));
                        setConfirming(null);
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
  const { doc } = plan;
  const rows = doc?.audit ?? [];
  const outstanding = useMemo(() => (doc ? select.outstandingRationales(doc) : []), [doc]);

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
          <button
            className="btn primary"
            disabled={!doc}
            onClick={() =>
              doc && csv.downloadCsv(`${doc.plan.year}_IAP_audit_trail.csv`, csv.auditRows(doc))
            }
          >
            Export audit trail to CSV
          </button>
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
  const { doc, run } = plan;
  const [edited, setEdited] = useState<Record<string, string> | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const data = doc?.reference ?? null;
  const impact = useMemo(() => (doc ? select.referenceImpact(doc) : null), [doc]);

  // The textareas start from the document and only diverge once someone types.
  const text = useMemo(
    () =>
      edited ??
      (data
        ? {
            taxonomy: data.taxonomy.map((t) => `${t.code} | ${t.label}`).join("\n"),
            business: data.business.map((t) => t.label).join("\n"),
            location: data.location.map((t) => t.label).join("\n"),
          }
        : {}),
    [edited, data],
  );

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
                onChange={(e) => setEdited({ ...text, [key]: e.target.value })}
              />
            </div>
          ))}
        </div>
        <div className="rowactions" style={{ marginTop: 10 }}>
          <button
            className="btn primary"
            onClick={() => {
              const lists: [ReferenceKind, boolean][] = [
                ["taxonomy", true],
                ["business", false],
                ["location", false],
              ];
              const ok = lists.every(
                ([kind, withCode]) =>
                  run((current) =>
                    workflow.replaceReference(current, {
                      kind,
                      entries: parse(text[kind] ?? "", withCode),
                    }),
                  ).ok,
              );
              setMessage(ok ? "Applied." : "Rejected — check the values.");
              if (ok) setEdited(null);
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

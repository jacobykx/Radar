"use client";

import { Fragment, useState } from "react";

import { Approval } from "@/components/Approval";
import { AuditTrail, ReferenceData, Versions } from "@/components/Governance";
import { Prestaging } from "@/components/Prestaging";
import { RiskRadar } from "@/components/RiskRadar";
import { ShapedPlan } from "@/components/ShapedPlan";
import { StagingCapacity } from "@/components/StagingCapacity";
import { csv, QUARTERS } from "@/lib/engine";
import { usePlan } from "@/lib/usePlan";

const TABS = [
  "Risk Radar",
  "Staging & capacity",
  "Shaped plan",
  "Approval",
  "Pre-staging (Helios)",
  "Versions",
  "Audit trail",
  "Reference data",
] as const;

export default function Page() {
  const plan = usePlan();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Risk Radar");
  const summary = plan.summary;

  const qMax = summary
    ? Math.max(1, ...Object.values(summary.fte_by_quarter), summary.annual_fte_quarters / 4)
    : 1;
  const qCap = summary ? Math.round(summary.annual_fte_quarters / 4) : 0;

  return (
    <div className="wrap">
      <header className="top">
        <div className="kicker">2027 Indicative Annual Planning · Planning Module</div>
        <h1>IAP Planning, Staging &amp; Capacity</h1>
        <div className="meta">
          2LOD assurance planning — consolidate, shape (capacity · priority · dedup), stage for L2
          sign-off, export to Helios.
        </div>
        <div className="who">
          {plan.identity ? (
            <>
              Working as <b>{plan.identity.username}</b> · roles{" "}
              <b>{plan.identity.roles.join(", ")}</b>
              <span style={{ opacity: 0.75 }}>
                — identity travels in the instance document for this POC; FRAME Auth Service
                supplies it in the deployed build
              </span>
            </>
          ) : (
            "Resolving identity…"
          )}
        </div>

        <div className="rowactions" style={{ marginTop: 10, marginBottom: 0 }}>
          <span className="muted small">
            Plan and workflow run in this page; the instance is served from{" "}
            <code>{plan.url}</code>
            {plan.doc && ` · ${plan.doc.plan.name} · revision ${plan.doc.revision}`}
          </span>
          <button
            className="btn sm"
            disabled={!plan.doc}
            onClick={() => plan.doc && csv.downloadInstance(plan.doc)}
            title="Download the working plan as an instance document — host that file to resume from it"
          >
            Export instance JSON
          </button>
          <button
            className="btn sm ghost"
            onClick={() => plan.reset()}
            title="Discard local changes and re-read the hosted instance"
          >
            Reset to hosted instance
          </button>
        </div>
      </header>

      {summary && (
        <div className="dashwrap" style={{ marginBottom: 18 }}>
          <div className="dashcard">
            <div className="dashttl">Plan funnel</div>
            <div className="funnel">
              {[
                [summary.candidates, "Candidates"],
                [summary.in_scope, "In scope"],
                [summary.descoped, "Descoped"],
                [summary.scheduled, "Scheduled"],
              ].map(([n, l], i, arr) => (
                <Fragment key={String(l)}>
                  <div className="fstep">
                    <div className="fn">{n}</div>
                    <div className="fl">{l}</div>
                  </div>
                  {i < arr.length - 1 && <div className="fsep">›</div>}
                </Fragment>
              ))}
            </div>
          </div>

          <div className="dashcard">
            <div className="dashttl">
              Capacity used{" "}
              <span className="muted">
                {summary.used_fte} of {summary.annual_fte_quarters}
              </span>
            </div>
            <div className="donut" style={{ ["--pct" as string]: Math.min(100, summary.utilisation_pct) }}>
              <span>{summary.utilisation_pct}%</span>
            </div>
          </div>

          <div className="dashcard">
            <div className="dashttl">
              FTE by quarter <span className="muted">capacity {qCap}/qtr</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 82 }}>
              {QUARTERS.map((q) => {
                const v = summary.fte_by_quarter[q] ?? 0;
                return (
                  <div
                    key={q}
                    style={{
                      flex: 1,
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "flex-end",
                      alignItems: "center",
                      height: "100%",
                    }}
                  >
                    <div
                      style={{
                        width: "100%",
                        minHeight: 3,
                        height: `${Math.round((v / qMax) * 100)}%`,
                        borderRadius: "4px 4px 0 0",
                        background: v > qCap ? "var(--over)" : "var(--blue)",
                      }}
                    />
                    <div className="fl">{q}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--navy)" }}>{v}</div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="dashcard">
            <div className="dashttl">Attention</div>
            <div className="attn">
              <div className={`ai ${summary.unscheduled ? "bad" : "good"}`}>
                <b>{summary.unscheduled}</b> unscheduled
              </div>
              <div className={`ai ${summary.outstanding_rationales ? "bad" : "good"}`}>
                <b>{summary.outstanding_rationales}</b> missing rationale
              </div>
              <div className={`ai ${summary.descoped ? "bad" : "good"}`}>
                <b>{summary.descoped}</b> descoped
              </div>
            </div>
          </div>
        </div>
      )}

      {plan.error && (
        <div className="banner err">
          {plan.error}{" "}
          <button className="btn sm ghost" onClick={() => plan.setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
            {t === "Audit trail" && summary && summary.outstanding_rationales > 0 && (
              <span className="pill">{summary.outstanding_rationales}</span>
            )}
          </button>
        ))}
      </div>

      {plan.loading ? (
        <div className="panel muted">Loading the plan…</div>
      ) : (
        <>
          {tab === "Risk Radar" && <RiskRadar plan={plan} />}
          {tab === "Staging & capacity" && <StagingCapacity plan={plan} />}
          {tab === "Shaped plan" && <ShapedPlan plan={plan} />}
          {tab === "Approval" && <Approval plan={plan} />}
          {tab === "Pre-staging (Helios)" && <Prestaging plan={plan} />}
          {tab === "Versions" && <Versions plan={plan} />}
          {tab === "Audit trail" && <AuditTrail plan={plan} />}
          {tab === "Reference data" && <ReferenceData plan={plan} />}
        </>
      )}

      <footer className="bottom">
        IAP Planning Module · staging &amp; capacity tool for the 2027 Indicative Annual Plan.
        Inputs: Risk Radar weighting and core externally-mandated reviews. Scoring, effort and
        capacity figures are indicative — calibrate with risk stewards before L2 governance.
      </footer>
    </div>
  );
}

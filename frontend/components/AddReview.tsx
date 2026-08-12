"use client";

import { useMemo, useState } from "react";

import { EFFORT_SIZES, workflow, type EffortSize, type Origin } from "@/lib/engine";
import type { PlanState } from "@/lib/usePlan";

/**
 * The two add-forms, as the prototype has them.
 *
 * Regulatory Assurance files a core externally-mandated review: it is pinned into the
 * plan and, given a go-live date, into that date's quarter. Risk Assurance files a
 * risk-led candidate, which lands in the backlog for the team to stage.
 *
 * Both require a rationale. Factor scores are absent from both forms by design -- they
 * are the scoring engine's to supply, so a new review starts at the neutral mid-point
 * and is restated when the engine next runs.
 */
export function AddReview({ plan }: { plan: PlanState }) {
  return (
    <>
      <AddForm
        plan={plan}
        origin="Regulatory Assurance"
        summary="➕ Regulatory Assurance"
        blurb="File a core externally-mandated review. It is pinned into the plan (★, always staged) and flows through staging, capacity, sign-off and Helios pre-staging."
        confirmLabel="Add mandated review"
        footnote="Ratings are not required — mandated reviews are compulsory and pinned regardless of score."
      />
      <AddForm
        plan={plan}
        origin="Risk Assurance"
        summary="➕ Risk Assurance"
        blurb="Add a risk-led (non-mandated) candidate review. The rationale is recorded against the review and in the audit trail. It enters the backlog for the team to stage."
        confirmLabel="Add review"
      />
    </>
  );
}

interface Draft {
  title: string;
  taxonomy_code: string;
  assurance_function: string;
  sub_team: string;
  effort_size: EffortSize;
  business: string;
  locations: string[];
  regulator: string;
  regulation: string;
  rris_ids: string;
  go_live: string;
  rationale: string;
}

const EMPTY: Draft = {
  title: "",
  taxonomy_code: "",
  assurance_function: "",
  sub_team: "",
  effort_size: "M",
  business: "",
  locations: [],
  regulator: "",
  regulation: "",
  rris_ids: "",
  go_live: "",
  rationale: "",
};

function AddForm({
  plan,
  origin,
  summary,
  blurb,
  confirmLabel,
  footnote,
}: {
  plan: PlanState;
  origin: Origin;
  summary: string;
  blurb: string;
  confirmLabel: string;
  footnote?: string;
}) {
  const { doc, run } = plan;
  const mandated = origin === "Regulatory Assurance";
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [added, setAdded] = useState<string | null>(null);

  const functions = useMemo(
    () => (doc?.assurance_functions ?? []).filter((f) => f.is_active).map((f) => f.name),
    [doc],
  );
  const subTeams = doc?.sub_teams[draft.assurance_function] ?? [];
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setAdded(null);
    setDraft({ ...draft, [key]: value });
  };

  if (!doc) return null;

  const submit = () => {
    const { ok, result } = run((current) =>
      workflow.addReview(current, {
        title: draft.title,
        origin,
        assurance_function: draft.assurance_function || functions[0],
        sub_team: draft.sub_team || null,
        taxonomy_code: draft.taxonomy_code || null,
        business: draft.business || null,
        locations: draft.locations,
        effort_size: draft.effort_size,
        rationale: draft.rationale,
        // Regulatory detail is the mandated form's alone; the risk-led form has no
        // obligation behind it to reference.
        regulator: mandated ? draft.regulator || null : null,
        regulation: mandated ? draft.regulation || null : null,
        rris_ids: mandated ? draft.rris_ids || null : null,
        go_live: mandated ? draft.go_live || null : null,
      }),
    );
    if (ok && result) {
      setAdded(result);
      setDraft(EMPTY);
    }
  };

  const field = (label: string, control: React.ReactNode, wide = false) => (
    <div className={`af ${wide ? "wide" : ""}`}>
      <label>{label}</label>
      {control}
    </div>
  );

  return (
    <details className="help">
      <summary>{summary}</summary>
      <div>
        <p className="muted small" style={{ marginTop: 0 }}>
          {blurb}
        </p>

        <div className="addgrid">
          {field(
            "Risk taxonomy L3",
            <select
              value={draft.taxonomy_code}
              aria-label={`${origin} taxonomy`}
              onChange={(e) => set("taxonomy_code", e.target.value)}
            >
              <option value="">— select —</option>
              {doc.reference.taxonomy.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </select>,
          )}
          {field(
            "Review title",
            <input
              type="text"
              value={draft.title}
              aria-label={`${origin} title`}
              placeholder={
                mandated
                  ? "e.g. New regulatory reporting return — first live submissions"
                  : "e.g. Thematic review of model change governance"
              }
              onChange={(e) => set("title", e.target.value)}
            />,
            true,
          )}
          {field(
            "Assurance function",
            <select
              value={draft.assurance_function}
              aria-label={`${origin} assurance function`}
              onChange={(e) => setDraft({ ...draft, assurance_function: e.target.value, sub_team: "" })}
            >
              <option value="">— select —</option>
              {functions.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>,
          )}
          {field(
            "Sub-team",
            <select
              value={draft.sub_team}
              aria-label={`${origin} sub-team`}
              disabled={subTeams.length === 0}
              onChange={(e) => set("sub_team", e.target.value)}
            >
              <option value="">{subTeams.length ? "— none —" : "n/a"}</option>
              {subTeams.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>,
          )}
          {field(
            "Effort",
            <select
              value={draft.effort_size}
              aria-label={`${origin} effort`}
              onChange={(e) => set("effort_size", e.target.value as EffortSize)}
            >
              {EFFORT_SIZES.map((s) => (
                <option key={s} value={s}>
                  {s} · {s === "S" ? 60 : s === "M" ? 90 : 120}d
                </option>
              ))}
            </select>,
          )}
        </div>

        <div className="addgrid">
          {field(
            "Business",
            <select
              value={draft.business}
              aria-label={`${origin} business`}
              onChange={(e) => set("business", e.target.value)}
            >
              <option value="">— select —</option>
              {doc.reference.business.map((b) => (
                <option key={b.code}>{b.label}</option>
              ))}
            </select>,
          )}
          {field(
            "Location(s)",
            <select
              value=""
              aria-label={`${origin} add location`}
              onChange={(e) =>
                e.target.value && set("locations", [...draft.locations, e.target.value])
              }
            >
              <option value="">+ add…</option>
              {doc.reference.location
                .filter((l) => !draft.locations.includes(l.label))
                .map((l) => (
                  <option key={l.code}>{l.label}</option>
                ))}
            </select>,
          )}
          <div className="af end">
            {draft.locations.length === 0 ? (
              <span className="muted small">No locations yet</span>
            ) : (
              draft.locations.map((l) => (
                <span className="locchip" key={l}>
                  {l}
                  <button
                    className="lx"
                    title={`Remove ${l}`}
                    onClick={() =>
                      set(
                        "locations",
                        draft.locations.filter((x) => x !== l),
                      )
                    }
                  >
                    ✕
                  </button>
                </span>
              ))
            )}
          </div>
        </div>

        {mandated && (
          <div className="addgrid">
            {field(
              "Regulator",
              <input
                type="text"
                value={draft.regulator}
                aria-label="Regulator"
                placeholder="e.g. PRA / FCA / BoE"
                onChange={(e) => set("regulator", e.target.value)}
              />,
            )}
            {field(
              "Regulation / obligation",
              <input
                type="text"
                value={draft.regulation}
                aria-label="Regulation"
                placeholder="e.g. PS7/26 — operational incident & third-party reporting"
                onChange={(e) => set("regulation", e.target.value)}
              />,
              true,
            )}
            {field(
              "RRIS ID(s)",
              <input
                type="text"
                value={draft.rris_ids}
                aria-label="RRIS IDs"
                placeholder="e.g. RRIS-10421, RRIS-10422"
                onChange={(e) => set("rris_ids", e.target.value)}
              />,
            )}
            {field(
              "Go-live date",
              <input
                type="date"
                value={draft.go_live}
                aria-label="Go-live date"
                title="Pins the review into this date's quarter"
                onChange={(e) => set("go_live", e.target.value)}
              />,
            )}
          </div>
        )}

        <div className="af" style={{ marginTop: 8 }}>
          <label>Review rationale (required)</label>
          <textarea
            value={draft.rationale}
            aria-label={`${origin} rationale`}
            placeholder={
              mandated
                ? "What the review covers and why — scope, obligation being assured, expected outcome…"
                : "Why is this review proposed? Events, near-misses, prior findings, stakeholder request, coverage gaps…"
            }
            onChange={(e) => set("rationale", e.target.value)}
          />
        </div>

        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
          <button
            className="btn primary"
            disabled={!draft.title.trim() || !draft.assurance_function}
            onClick={submit}
          >
            {confirmLabel}
          </button>
          {added && (
            <span className="small" style={{ color: "var(--ok)" }}>
              Added <b>{added}</b>
              {mandated
                ? " — pinned into the plan; set a quarter on Staging & capacity if it has no go-live date."
                : " — in the backlog; tick Stage to bring it into the plan."}
            </span>
          )}
        </div>

        {footnote && (
          <div className="muted small" style={{ marginTop: 6 }}>
            {footnote}
          </div>
        )}
      </div>
    </details>
  );
}

# Build plan — 2027 IAP Planning Module

Derived from `BUILD_INSTRUCTIONS.md`, `CLAUDE.md` and a full read of the prototype
`2027_IAP_Planning_Module.html` (1,536 lines). The prototype is the functional spec; every
behaviour below is traced to it by line number so the port is checkable rather than remembered.

---

## 0. Shape of the work

Two deployables in one repo:

```
iap-planning/
  backend/                 Poetry · FastAPI · SQLAlchemy · Alembic · Pydantic
    app/
      api/                 routers — thin; parse, call service, serialise
      services/            ALL domain logic lives here (priority, capacity, waterfall,
                           routing, descope cascade, snapshot/restore)
      models/              SQLAlchemy ORM
      schemas/             Pydantic in/out — read-only fields enforced here
      auth/                gateway identity dependency -> (username, ad_groups)
      seed/                synthetic fixtures ported from the prototype
    migrations/            Alembic, every one reversible
    tests/                 pytest — domain rules first (section 4)
  frontend/                Next.js · TypeScript
    app/                   one route per stage tab
    lib/api/               GENERATED from the FastAPI OpenAPI schema — never hand-written
    components/
    __tests__/             jest
```

Non-negotiables carried straight through: no hand-rolled auth; the frontend renders and calls,
it never decides; every rule enforced server-side; no `alert`/`prompt`/`confirm` — rationale is
captured inline exactly as the prototype does (proto:837, 848).

> **POC deviation (D5).** The repository as it stands runs the workflow in the browser against a
> JSON instance, so `frontend/lib/api/` is replaced by `frontend/lib/engine/` and the generated
> client is gone. Everything below describes the deployed build, which `backend/` still implements.

---

## 1. Domain model

Normalised out of the prototype's flat `REVIEWS` + `state[ref]` structure.

| Table | Columns (beyond id/created/updated) | Source in prototype |
|---|---|---|
| `assurance_function` | name, fte_per_quarter, is_active | `AF_VALUES` (proto:661), `TEAM_FTE` (proto:996) |
| `sub_team` | assurance_function_id, name | `SUBTEAMS` (proto:610), `RT_VALUES` (proto:662) |
| `plan` | year, name, status | implicit (single 2027 plan) |
| `review` | plan_id, ref, title, origin(enum), mandated, taxonomy_code, assurance_function_id, sub_team_id, business, effort_size(enum S/M/L), fte_override, regulator, regulation, rris_ids, rca_linked, go_live_date, is_custom | `REVIEWS` (proto:577), `REG_SEED` (proto:1098), `RCA_LINKED` (proto:1096) |
| `review_location` | review_id, location (m2m) | `; `-joined string on helios.location (proto:624) |
| `review_score` | review_id, risk, urgency, coverage_gap, change_index, as_at, source | `reg/change/coverage/risk` on the review (proto:578) |
| `priority_weight` | plan_id, a_risk, b_urgency, c_coverage, d_change, version, set_by, set_at | `weights` (proto:710) |
| `plan_item` | review_id (1:1), staged, planned_quarter, priority_override, priority_override_rationale, descope_rationale, row_version | `state[ref]` (proto:731) |
| `helios_prestaging` | review_id, + the 26 fields | `HELIOS_FIELDS` (proto:663) |
| `approval` | review_id, route(enum IRR/RCA/Standard), gate, status(enum), approver, decided_at, comment | `state.approvals` (proto:1111) |
| `steward_consultation` | review_id, steward_name, recorded_by, recorded_at | `stewardState` (proto:727) |
| `review_note` | review_id, author, created_at, text | `state.comments` (proto:832) |
| `audit_entry` | review_id (nullable), action, detail, username, created_at | `audit` (proto:752) — **append-only** |
| `plan_version` | plan_id, name, note, author, created_at, snapshot JSONB | `versions` (proto:1336) |
| `reference_data` | kind(enum taxonomy/business/location), code, label, sort_order, active | `REF_DEFAULT` (proto:557) |

Notes on the normalisation:
- **Effort is stored as the size enum, not days.** Days (60/90/120) and default FTE (2/3/4) are
  derived constants; `fte_override` beats the default (proto:600-604). The prototype's free-form
  `effort` days field is a legacy artefact snapped to the three sizes on load (proto:608, 750).
- **Locations** are ordered by reference-list order on write (proto:625-627). Keep that so exports
  are stable.
- `review_score` is insert-only with an `as_at` — the scoring engine restates, it does not edit.
- `plan_item.row_version` gives optimistic concurrency (the prototype is single-user localStorage;
  the build is not — see risk R2).

---

## 2. Domain logic — the services layer

Each of these is a pure function over loaded state, so it is unit-testable without HTTP.

**`scoring.py`**
- `computed_priority(scores, weights)` = `(a·risk + b·urgency + c·coverage + d·change) / (a+b+c+d)`,
  denominator falling back to 1 when all weights are zero (proto:758).
- `effective_priority` = override if set else computed (proto:760). Both persisted separately;
  the computed value is never written over.
- `band(v)`: ≥4.3 Critical · ≥3.7 High · ≥3.0 Medium · else Low (proto:761).
- Mandated reviews return the label `Mandated` and no numeric priority (proto:762-764).

**`capacity.py`**
- `quarter_demand(function, quarter)` = Σ FTE of staged, non-descoped reviews in that function and
  quarter (proto:998).
- Annual capacity = `fte_per_quarter × 4` FTE-quarters; mandated demand is committed first, the
  remainder is headroom (proto:1008-1010).

**`scheduling.py` — waterfall** (proto:1073-1091). Per assurance function:
1. Mandated reviews that already hold a quarter (derived from go-live) keep it and consume capacity
   first.
2. Remaining staged reviews queue mandated-first, then by effective priority descending.
3. Each is placed in the **earliest** quarter where `load + fte ≤ capacity`; if none fits it is
   left unscheduled and reported as unplaced. Never over-fill.
4. Returns `{placed, unplaced}` and writes one audit entry for the run.

**`staging.py`** — descope cascade. A descoped review is excluded from staging totals, capacity,
approval scope, pre-staging and the plan (proto:989, 1002, 1118). Greyed, not deleted, in Risk Radar.

**`approval.py`** — exactly one gate per review, routed: `IRR` if mandated, else `RCA` if RCA-linked,
else `Standard` (proto:1109-1110). Approve completes it; **Return requires a comment** (proto:1128).
Cross-team linkage: other staged IRR reviews sharing an RRIS ID or the same regulation string
(proto:1106).

**`helios.py`** — the 26-field set, allowed-value lists, 7 required fields for the completeness flag
(proto:692), Plan/IAP quarter and year derived from Target Start Date (proto:698, 1226).

**`versions.py`** — snapshot = plan_items + weights + overrides + custom reviews + pre-staging + 
approvals + steward records. Restore replaces that state and is itself audited (proto:1319-1347).
Audit entries are **not** in the snapshot and are never rolled back.

**`audit.py`** — one write path, append-only. No update or delete endpoint, and the prototype's
"Clear log" button (proto:450) is dropped — see decision D3.

---

## 3. API surface

As per the brief's section 5, plus what the prototype needs and the brief omits:

```
GET    /reference-data                         PUT /reference-data           (admin)
GET    /reference-data/impact                  orphaned values still in use (proto:1401)
GET    /reviews                                filters: team, sub_team, business, location,
                                               origin, route, status, quarter
POST   /reviews                                Regulatory Assurance | Risk Assurance
PATCH  /reviews/{id}                           title, size, fte, business, taxonomy, reg fields
PUT    /reviews/{id}/locations
POST   /reviews/{id}/priority-override         400 without rationale
DELETE /reviews/{id}/priority-override
POST   /reviews/{id}/stage                     see D1
PATCH  /reviews/{id}/quarter
POST   /reviews/{id}/steward
POST   /reviews/{id}/notes                     decision log (proto:864)
GET    /plan/weights                           PUT /plan/weights
GET    /plan/summary                           funnel + capacity cards (proto:779)
POST   /plan/autofill                          -> {placed, unplaced}
GET    /capacity                               per function/quarter: capacity, demand, headroom
GET    /plan/shaped                             Gantt data      GET /plan/export.csv
GET    /approvals                              + dashboard aggregates for the filtered view
POST   /reviews/{id}/approval                  400 returning without comment
POST   /approvals/bulk-approve                 approve all matching the supplied filter
GET    /prestaging  /  PATCH /prestaging/{id}  GET /prestaging/export
GET/POST /versions                             POST /versions/{id}/restore   DELETE /versions/{id}
GET    /audit                                  GET /audit/export   GET /audit/outstanding
```

Read-only enforcement: the four factor scores are absent from every request schema, and
`PATCH /reviews/{id}` rejects them with 422 rather than ignoring them — silent drops hide bugs.

RBAC from the AD groups supplied by the authentication gateway:

| Role | Can |
|---|---|
| Planner | stage, descope, override priority, set quarter/size/FTE/location, notes, pre-staging |
| Approver | approve / return, bulk approve |
| Admin | reference data, capacity config, version restore |
| Reader | GET only |

---

## 4. Tests before UI (brief §6)

`backend/tests/test_domain_rules.py` — written first, one test per methodology rule:

1. weighted priority normalises by the weight sum; all-equal weights = plain mean; zero weights
   do not divide by zero
2. priority override without rationale → 400; computed value survives the override
3. `DELETE` override restores the computed value
4. mandated review is never driver-scored and reports `Mandated`
5. origin and the mandated flag cannot disagree (mandated ⇒ Regulatory Assurance)
6. descope without rationale → 400 (per D1)
7. descoped review disappears from staging, capacity, approval, pre-staging and the plan
8. size→days and size→default-FTE mapping; FTE override wins
9. waterfall never exceeds quarterly FTE
10. waterfall fills earliest-first, mandated before priority order
11. waterfall reports unplaced reviews instead of over-filling
12. mandated review with a fixed quarter holds its slot through auto-fill
13. route selection IRR / RCA / Standard; exactly one gate
14. return without comment → 400; approve completes the gate
15. audit has no update or delete path (asserted against the router table, not by convention)
16. version restore round-trips every piece of state; audit is not rolled back
17. multi-location filter matches if any location matches

Jest covers rendering and the inline rationale flows (no browser dialogs), not the maths.

---

## 5. Build order — vertical slices

| # | Slice | Ends with |
|---|---|---|
| 1 | Skeleton | Project scaffold, Postgres, first migration, `/permission` wiring, Next.js shell, generated client, one review listed from the DB |
| 2 | Domain tests | Section 4 red, then the services layer green — no UI yet |
| 3 | Risk Radar | scores read-only, weights, priority + override, origin, steward, staging, descope, both add-forms, toolbar + column filters, sortable columns |
| 4 | Staging & capacity | quarters, size/FTE edit, bottom-up fill, quarterly demand vs capacity, waterfall, clear quarters |
| 5 | Shaped plan + Approval | quarter Gantt by function, routes, sign-off, bulk approve, filter-reactive dashboards, regulatory ref + cross-team linkage, CSV exports |
| 6 | Pre-staging + reference data | 26 Helios fields, derived quarter/year, completeness flag, Helios export, KBD service call with the admin screen as fallback |
| 7 | Governance | audit trail, outstanding rationales, versions, RBAC by AD Group |
| 8 | Hardening | test coverage, lint, CVE clearance, non-functionals, UAT |

Each slice: migration → service → tests → API → generated client → UI → jest.

---

## 6. Decisions (D — settled) and risks (R)

**D0 — repository.** Scaffolded from scratch to the layout in section 0; there was no existing
template to start from.

**D5 — POC topology. SETTLED: the UI hosts the workflow; the instance is JSON.** For the
proof of concept the methodology runs in the browser, as it does in the prototype, and the
plan is a JSON instance document served as a static file (`frontend/public/instances/`,
overridable with `NEXT_PUBLIC_INSTANCE_URL`). `frontend/lib/engine/` is a straight port of
`backend/app/domain` plus the command half of `backend/app/services`; `backend/` is
untouched and remains the productionisation target. The two seams that reverse this are
`engine/instance.ts` (where the document comes from) and `engine/workflow.ts` (what may
change it) — sections 1-4 above describe the deployed build and still stand. What the POC
gives up: rules are enforced client-side, identity and roles travel in the instance
document rather than coming from an authentication gateway, and the working copy is per-browser
`localStorage`, so it is single-user. `row_version` is carried through the engine anyway,
so R2 does not need re-plumbing later. The rules are now stated twice, in Python and
TypeScript, and both copies carry the section 4 tests — that duplication is the cost of
the POC and ends when the UI is pointed back at the API.

**D1 — descope strictness. SETTLED: reject.** The brief says `POST /stage` returns 400 when
descoping without a rationale. The prototype is looser: the Risk Radar checkbox un-stages
immediately and logs "reason pending", and the review is then flagged in an "outstanding
rationales" panel (proto:914, 1219); only the explicit *Descope review* button demands the
rationale inline (proto:940-946). We follow the brief — the API rejects — and the outstanding
panel becomes a data-quality report over seeded, imported and restored records rather than a
live queue. The Risk Radar checkbox therefore opens the inline rationale box instead of
un-staging on the spot.

**D2 — SME / resource-allocation machinery. SETTLED: dropped from the MVP.** The prototype still
carries a 14-person SME roster, skills, day-level allocation and coverage checks (proto:643-658,
766-770, 1435); the brief's data model, stage list and capacity rule contain none of it. Capacity
is FTE per quarter per assurance function. `staffedTeams()` (proto:988) derived the capacity
roll-up from the SME roster — that becomes an explicit `assurance_function.is_active` flag.
SME assignment is a later ticket, not this build.

**D3 — "Clear log". SETTLED: dropped.** The prototype has a Clear log button on the audit trail
(proto:450). Brief rule 11 says append-only with no delete endpoint.

**D4 — Phase 2 GenAI tab.** Static roadmap content plus one templated mock generator (proto:507).
Ported as a static page; no model calls, no backend.

**R1 — reference data is the join key.** Taxonomy `code` is stored on the review, so a KBD
re-issue that renames codes orphans reviews. The prototype already degrades gracefully (unknown
codes still display, proto:574) and warns about orphans; keep both, and never cascade-delete
reference data.

**R2 — concurrency.** The prototype is single-user localStorage; the build is multi-user. Every
`plan_item` write carries `row_version`; a stale write returns 409 and the UI re-fetches. Waterfall
auto-fill takes a plan-level advisory lock so two users cannot interleave a re-schedule.

**R3 — seeded data.** All 20 seeded reviews, `REG_SEED`, `RCA_LINKED`, `BIZ_SEED`, `LOC_SEED` and
`SUBTEAM_SEED` are mock and safe to port as synthetic fixtures. They must load through the seed
module, never through a migration, so PROD can start empty.

**R4 — `golive` parsing.** The prototype parses free-text go-live dates ("18 Mar 2027", "Sep 2026",
proto:694). Store a real `date` column and do the parsing once, in the seed.

# 2027 IAP Planning Module

A 2LOD assurance planning tool: turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios. Target platform is **FRAME**.

See [PLAN.md](PLAN.md) for the build plan, data model and settled decisions.

---

## How this POC is put together

The workflow runs **in the UI**, the way the HTML prototype does, and the plan it works
on is a **JSON instance document** served as a static file. There is no database and no
backend process in the loop:

```
frontend/public/instances/2027-iap.json   the instance — reference data, capacity,
                                          20 candidate reviews, plan state
frontend/lib/engine/                      the workflow — scoring, capacity, waterfall,
                                          staging, sign-off, Helios, versions, audit
frontend/lib/usePlan.ts                   loads the instance, runs commands, persists
frontend/components/                      screens: render and call, never decide
```

The instance document is loaded once, held in the browser, and every change is applied
to it by a command in `lib/engine/workflow.ts`. Two rules hold for every command: a
methodology violation throws and leaves the document untouched, and a successful change
appends to the audit trail in the same step. Screens read through `lib/engine/select.ts`
and write through `plan.run(...)` — the same split the API enforced, moved inside the
page.

**The FastAPI service in `backend/` is unchanged and still the productionisation
target.** Nothing was deleted from it; the POC simply does not call it. Two seams make
the swap back a local change: `engine/instance.ts` (where the document comes from) and
`engine/workflow.ts` (what may change it). Point the first at `GET /reviews` and move
the second behind the API, and the screens above are untouched.

### What the POC gives up, deliberately

| | POC | Deployed build |
|---|---|---|
| Rule enforcement | in the browser | server-side, un-bypassable |
| Identity and roles | carried in the instance document | FRAME Auth Service |
| Concurrency | `row_version` checked locally; one user | 409 against a shared database |
| Persistence | `localStorage`, plus export/import of the JSON | Postgres |

Client-side role checks demonstrate the rule, they do not secure it — anything running
in a browser can be edited by the person running it. That is the reason the rules also
exist in `backend/app/domain`, and the reason both copies are covered by tests.

---

## Running it

One process.

```bash
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:3010**. The instance loads from
`/instances/2027-iap.json`; `NEXT_PUBLIC_INSTANCE_URL` points the UI at any URL that
returns the same shape — an object store, a CDN, a colleague's edited copy:

```bash
NEXT_PUBLIC_INSTANCE_URL=https://example.internal/plans/2027-draft.json npm run dev
```

### Working with instances

- **Export instance JSON** (top of the page) downloads the working plan in the same
  schema it was loaded from. Host that file and the next session starts where this one
  finished — that is the whole "hosting through JSON" loop.
- **Reset to hosted instance** discards the local working copy and re-reads the file.
- Edits live in `localStorage` under `iap.instance.<id>`, so a reload resumes; nothing
  is ever written back to the hosted file.

### Regenerating the shipped instance

`frontend/public/instances/2027-iap.json` is generated from the same synthetic fixtures
the backend seeds from, so the two cannot drift:

```bash
cd backend && python3 -m scripts.export_instance
```

No dependencies, no database — `app/seed/data.py` is plain Python. Edit the fixtures
there and re-run, or hand-edit the JSON for a one-off scenario.

---

## What to try

| Stage | Worth exercising |
|---|---|
| **Risk Radar** | Factor scores are read-only — there is no control to edit them. Type a new Priority, then confirm in the drawer: the override needs a rationale, and the computed value survives beside it. Un-ticking Stage opens the descope box rather than un-staging on the spot. |
| **Staging & capacity** | *Auto-fill quarters* runs the waterfall: Q1 first, mandated before priority, never exceeding a function's quarterly FTE. Anything that will not fit is reported, not absorbed. Shrink a function's `fte_per_quarter` in the instance JSON and re-run to see reviews come back unplaced. |
| **Shaped plan** | The quarter Gantt by assurance function, and CSV export. |
| **Approval** | One gate per review, routed IRR / RCA / Standard. Approving needs no comment; returning does. The dashboard cards recalculate to whatever the filters show. |
| **Pre-staging** | Plan and IAP quarter/year are derived from Target Start Date and cannot be typed. The completeness flag tracks the 7 required fields. |
| **Versions** | Save a baseline, change the plan, restore it. The audit trail is not rolled back — restoring is itself an audited event. |
| **Audit trail** | Append-only. The engine exposes no command that edits or removes an entry, and the test suite asserts that against the command list. |

To see the role rules bite, set `identity.roles` in the instance JSON to `["Reader"]`
and reload — every write is refused with the role it needed.

---

## Tests

The methodology moved into the browser, so its tests did too. Both suites cover the
same numbered rules from `BUILD_INSTRUCTIONS.md` section 2.

```bash
cd frontend && npm test        # 64 cases — the engine
cd frontend && npm run typecheck
```

`__tests__/domain-rules.test.ts` mirrors `backend/tests/test_domain_rules.py` case for
case; `__tests__/workflow.test.ts` covers the refusals, the audit trail and version
restore; `__tests__/instance.test.ts` covers loading a hosted document, including the
shipped one.

The backend suite still runs unchanged:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/pip install pytest ruff
cd backend && .venv/bin/python -m pytest        # 35 cases — the services layer
```

---

## Running the backend (unchanged, not required for the POC)

Nothing in the UI calls it, but it is still the deployment target and still runs:

```bash
cd backend && cp .env.example .env
cd backend && .venv/bin/python -m scripts.bootstrap --reset
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8010 --reload
```

Swagger at [/docs](http://127.0.0.1:8010/docs). `IAP_AUTH_DEV_MODE` supplies a synthetic
user locally and **must stay false in every deployed environment** — with it on, any
unauthenticated caller is granted every role. It defaults to false and the server logs a
warning on every start when it is on.

---

## Moving this into another repository

The tracked files are the whole deliverable — no secrets. Everything regenerable is
git-ignored: virtualenvs, `node_modules`, `.next`, the SQLite database.

```bash
git remote add origin <new-repo-url> && git push -u origin <branch>
```

### Change on arrival

| Where | Why |
|---|---|
| `NEXT_PUBLIC_INSTANCE_URL` | Points at the hosted instance for that environment |
| `backend/.env` per environment | `IAP_DATABASE_URL` to Postgres, `IAP_AUTH_DEV_MODE=false`, `IAP_CORS_ORIGINS` |
| Ports **8010** / **3010** | Local choices only — FRAME serves both behind the platform |
| `frontend/next.config.mjs` | `allowedDevOrigins` is a development-only workaround |
| Branch names | FRAME's Jenkins triggers on `feature/all/<JIRA-TICKET>` |

---

## Known gaps

- **The POC is single-user by construction.** The working copy is per-browser; two
  people editing the same hosted instance will not see each other. That is what the
  backend exists to fix, and is why `row_version` is carried through the engine
  unchanged rather than dropped.
- **Rules are enforced client-side in this mode** — see the table above.
- **No component tests yet.** The engine is covered; rendering is not (IAP-27).
- **Alembic migrations are not written yet** (IAP-3). Local backend schema comes from
  `scripts.bootstrap`, which is development-only.
- **Integrations are stubs**: the scoring engine, RCA/RRIS linkage and the Helios KBD
  reference-data feed are synthetic. In the POC they are fields in the instance
  document; that document is the seam where the real feeds land (IAP-22, IAP-24,
  IAP-25).
- **The Phase 2 GenAI tab is not ported** — roadmap content, no behaviour.

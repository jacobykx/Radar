# 2027 IAP Planning Module

A 2LOD assurance planning tool: turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios. Target platform is **FRAME**.

See [PLAN.md](PLAN.md) for the build plan, data model and settled decisions.

---

## Running it locally

Two processes. Start the backend first — the frontend's typed client is generated from
its OpenAPI schema.

### Backend — http://127.0.0.1:8010

FRAME uses Poetry, so `poetry install && poetry run ...` is the canonical path. On a
machine without Poetry, a plain venv works — dev dependencies live in Poetry's dev
group, which pip cannot read, so pytest is installed separately:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/pip install pytest ruff
```

Create the local configuration. `auth_dev_mode` defaults to **false** so a deployment
that forgets to configure it fails closed with a 401 rather than accepting anonymous
callers as administrators — local development opts in through this file, which is
git-ignored:

```bash
cd backend && cp .env.example .env
```

Create the schema and load the synthetic fixtures — 20 reviews ported from the
prototype. `--reset` drops every table first, so re-run it any time to get back to a
clean plan:

```bash
cd backend && .venv/bin/python -m scripts.bootstrap --reset
```

Start it. Swagger is at [/docs](http://127.0.0.1:8010/docs):

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8010 --reload
```

### Frontend — http://127.0.0.1:3010

```bash
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:3010**.

### Regenerating the API client

`frontend/lib/api/generated/schema.d.ts` is generated from the backend's OpenAPI schema
and **is committed**, so the repo type-checks and builds without a running backend.
Never hand-write or hand-edit it — regenerate it whenever the API contract changes, with
the backend running:

```bash
cd frontend && npm run generate:api
```

It reads `NEXT_PUBLIC_API_BASE` and falls back to `http://127.0.0.1:8010`. Regenerating
is what turns a backend contract change into a compile error rather than a runtime one,
so run it before assuming a frontend break is a frontend bug.

---

## What to try

| Stage | Worth exercising |
|---|---|
| **Risk Radar** | Factor scores are read-only — there is no control to edit them. Type a new Priority, then confirm in the drawer: the override needs a rationale, and the computed value survives beside it. Descope a review and watch it drop out of every later stage. |
| **Staging & capacity** | *Auto-fill quarters* runs the waterfall: Q1 first, mandated before priority, never exceeding a function's quarterly FTE. Anything that will not fit is reported, not absorbed. Shrink a function's capacity in the seed and re-run to see reviews come back unplaced. |
| **Shaped plan** | The quarter Gantt by assurance function, and CSV export. |
| **Approval** | One gate per review, routed IRR / RCA / Standard. Approving needs no comment; returning does. The dashboard cards recalculate to whatever the filters show. |
| **Pre-staging** | Plan and IAP quarter/year are derived from Target Start Date and cannot be typed. The completeness flag tracks the 7 required fields. |
| **Versions** | Save a baseline, change the plan, restore it. The audit trail is not rolled back — restoring is itself an audited event. |
| **Audit trail** | Append-only. There is no edit or delete endpoint, and `DELETE /audit` returns 405. |

### Local identity

There is no FRAME in front of the API locally, so `IAP_AUTH_DEV_MODE=true` in `.env`
supplies a synthetic user holding all three roles. To exercise RBAC, send the headers
FRAME would:

```bash
curl -H "x-frame-user: someone" -H "x-frame-ad-groups: IAP_READER" http://127.0.0.1:8010/permission
```

A reader gets 403 on any write. **`IAP_AUTH_DEV_MODE` must stay false in every deployed
environment** — with it on, any unauthenticated caller is granted every role. It
defaults to false and the server logs a warning on every start when it is on.

---

## Moving this into another repository

The tracked files are the whole deliverable — 67 files, ~600 KB, no secrets. Everything
regenerable is git-ignored: virtualenvs, `node_modules`, `.next`, the SQLite database,
and `frontend/lib/api/generated/` (rebuilt with `npm run generate:api`).

Either push this history to the new remote:

```bash
git remote add origin <new-repo-url> && git push -u origin feature/all/IAP-1
```

or export a clean snapshot of the tracked files only:

```bash
git archive --format=tar HEAD | tar -x -C <path-to-new-repo>
```

### Change on arrival

| Where | Why |
|---|---|
| `backend/.env` per environment | `IAP_DATABASE_URL` to Postgres, `IAP_AUTH_DEV_MODE=false`, `IAP_CORS_ORIGINS` to the deployed frontend |
| Ports **8010** / **3010** | Local choices only — 8000 was already in use on the development machine. FRAME serves both behind the platform |
| `frontend/next.config.mjs` | `allowedDevOrigins` is a development-only workaround; `NEXT_PUBLIC_API_BASE` should come from environment configuration |
| `frontend/package.json` | The `generate:api` URL points at localhost |
| Branch names | FRAME's Jenkins triggers on `feature/all/<JIRA-TICKET>`; this history uses IAP-1 |

### Still to build there

Alembic migrations (IAP-3), jest configuration and specs (IAP-27), the Jenkins job
configuration, and a Postgres run — none of which could be produced or verified on the
development machine, which has no Poetry, Postgres or Docker.

---

## Tests

```bash
cd backend && .venv/bin/python -m pytest
```

If this reports `No module named pytest`, the dev dependencies were not installed —
see the venv step above.

35 cases covering the methodology in `BUILD_INSTRUCTIONS.md` section 2. They are written
against the services layer, before the UI, so a later refactor cannot quietly break the
rules.

---

## Known gaps

- **Alembic migrations are not written yet.** Local schema comes from
  `scripts.bootstrap`, which is development-only. FRAME deployment needs a reversible
  initial migration (IAP-3).
- **No jest tests yet** — the `npm test` script exists but has no configuration or specs
  behind it (IAP-27).
- **Postgres is untested here.** Models target Postgres (JSONB) with SQLite variants for
  local development; the SQLite fallback is not a deployment target.
- **Integrations are stubs**: the scoring engine, RCA/RRIS linkage and the Helios KBD
  reference-data feed are seeded as synthetic data. `reference.fetch_from_kbd()` is the
  seam where the real feed lands (IAP-22, IAP-24, IAP-25).
- **The Phase 2 GenAI tab is not ported** — roadmap content, no behaviour.

# 2027 IAP Planning Module

A 2LOD assurance planning tool: turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios. Target platform is **FRAME**.

See [PLAN.md](PLAN.md) for the build plan, data model and settled decisions.

---

## Running it locally

```bash
make setup     # Poetry + npm install, and writes backend/.env
make reset     # migrate to head, then load the 20 synthetic reviews
make dev       # prints the two commands to run
```

Then, in two terminals:

```bash
make dev-backend    # http://127.0.0.1:8010 — Swagger at /docs
make dev-frontend   # http://127.0.0.1:3010
```

`make help` lists every target. The rest of this section is what those targets do, for
anyone who would rather run the steps by hand.

### Backend — http://127.0.0.1:8010

FRAME uses Poetry, so `poetry install && poetry run ...` is the canonical path, and
`poetry.lock` is committed so every machine resolves the same versions:

```bash
cd backend && poetry config virtualenvs.in-project true --local && poetry install
```

Create the local configuration. `auth_dev_mode` defaults to **false** so a deployment
that forgets to configure it fails closed with a 401 rather than accepting anonymous
callers as administrators — local development opts in through this file, which is
git-ignored:

```bash
cd backend && cp .env.example .env
```

Create the schema and load the synthetic fixtures — 20 reviews ported from the
prototype. The schema comes from Alembic, the same migrations a deployed environment
runs, so a local database cannot drift from what SIT, UAT and PROD get. `--reset`
downgrades to base first, so re-run it any time to get back to a clean plan:

```bash
cd backend && .venv/bin/python -m scripts.bootstrap --reset
```

Start it:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8010 --reload
```

### Frontend — http://127.0.0.1:3010

```bash
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:3010**.

### Postgres, in containers

The SQLite fallback is convenient but it is not what gets deployed — it has no JSONB, no
concurrent writers and no transactional DDL. To develop against the real thing:

```bash
make docker-up      # Postgres + migrations + API + frontend
make docker-seed    # load the fixtures
make docker-down    # stop, and drop the volume
```

`docker compose` runs `alembic upgrade head` as its own `migrate` service and the API
waits for it to finish, so the service never starts against a schema older than its
code. Migrations are deliberately *not* run from the container entrypoint — a schema
change is a deploy step with its own approval, not a side effect of a container
starting.

To point the native setup at a Postgres instead of SQLite, override the URL:

```bash
make reset DATABASE_URL=postgresql+psycopg://iap:iap_local_dev@127.0.0.1:5432/iap
```

### Migrations

```bash
make migrate                             # alembic upgrade head
make migration M="add widget table"      # autogenerate a revision
```

Autogenerate produces a **draft**: read it before committing. `alembic check` — which CI
runs — fails the build if a model was changed without a matching revision, so the two
cannot drift apart silently.

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

## Deploying it

The tracked files are the whole deliverable — no secrets. Everything regenerable is
git-ignored: virtualenvs, `node_modules`, `.next`, the SQLite database, and CI reports.
`poetry.lock`, `package-lock.json` and the generated API client **are** committed, so a
build is reproducible and the repo type-checks without a running backend.

### Configuration

`backend/.env.deployed.example` is the template for SIT, UAT and PROD. Its values belong
in the platform's configuration and secret store, never in the repository or an image.
Three of them are not optional:

| Setting | In a deployed environment |
|---|---|
| `IAP_DATABASE_URL` | Postgres. The SQLite fallback has no JSONB, no concurrent writers and no transactional DDL |
| `IAP_AUTH_DEV_MODE` | **false.** With it on, any unauthenticated caller is granted planner, approver *and* admin |
| `IAP_CORS_ORIGINS` | The deployed frontend origin. Never `*` — the API trusts role-bearing headers |

### Schema

`alembic upgrade head`, as an explicit deploy step. It is not run from the container
entrypoint: a schema change carries its own approval and should not be a side effect of
a container restarting. The initial revision is reversible — CI applies it, reverses it
and re-applies it on every build.

### Change on arrival

| Where | Why |
|---|---|
| Ports **8010** / **3010** | Local choices only — 8000 was already in use on the original development machine. FRAME serves both behind the platform |
| `frontend/next.config.mjs` | `allowedDevOrigins` is a development-only workaround; `NEXT_PUBLIC_API_BASE` should come from environment configuration |
| `frontend/package.json` | The `generate:api` URL points at localhost |
| `Jenkinsfile` | The agent label and credential IDs are placeholders, confirmed during FRAME onboarding |
| Branch names | FRAME's Jenkins triggers on `feature/all/<JIRA-TICKET>` |

`NEXT_PUBLIC_API_BASE` is inlined into the client bundle at build time, so a different
backend URL means a different frontend image — pass it as a build argument, not a
runtime variable.

---

## CI

`.github/workflows/ci.yml` runs on GitHub; `Jenkinsfile` describes the same stages for
FRAME. Both run:

| Check | Catches |
|---|---|
| `ruff check` | Lint |
| `pytest` | The 35 methodology cases |
| `alembic upgrade` → `downgrade` → `upgrade` | A migration that is not reversible |
| `alembic check` | A model changed without a matching revision |
| `tsc --noEmit`, `jest`, `next build` | Frontend type, logic and build breaks |
| `npm run generate:api` + `git diff --exit-code` | A committed API client that has gone stale against the backend |

The backend job runs against a Postgres 16 service container, not the SQLite fallback,
so dialect-specific problems fail in CI rather than in an environment.

Locally, `make check` runs the same set.

---

## Tests

```bash
make test           # both suites
make test-backend   # pytest — 35 cases
make test-frontend  # jest — 13 cases
```

The backend's 35 cases cover the methodology in `BUILD_INSTRUCTIONS.md` section 2. They
are written against the services layer, before the UI, so a later refactor cannot quietly
break the rules.

The frontend's 13 cases cover `errorMessage` — the API's rejection is what the user is
shown, so the UI never pre-empts a rule — and `usePlan`'s load, failure and resync paths.
They stub `fetch` at setup module scope, because openapi-fetch captures `globalThis.fetch`
when the client is constructed: a stub installed any later would leave the specs quietly
talking to a real backend.

If `make test-backend` reports `No module named pytest`, the dev dependencies were not
installed — run `make setup-backend`.

---

## Known gaps

- **Integrations are stubs**: the scoring engine, RCA/RRIS linkage and the Helios KBD
  reference-data feed are seeded as synthetic data. `reference.fetch_from_kbd()` is the
  seam where the real feed lands (IAP-22, IAP-24, IAP-25).
- **The Phase 2 GenAI tab is not ported** — roadmap content, no behaviour.
- **The container images have not been built.** The Dockerfiles and `docker-compose.yml`
  are written and the compose file validates, but the machine they were authored on had
  no Docker daemon, so `docker compose up --build` is unproven.
- **The Jenkins job itself is not configured.** `Jenkinsfile` describes the stages; the
  job, agent labels and credential IDs come from FRAME onboarding.
- **Frontend coverage is thin.** The specs cover `lib/`; the six stage components are
  currently exercised only through the API contract and the production build.

### Closed since the first cut

- ~~Alembic migrations (IAP-3)~~ — an initial revision now generates the full 15-table
  schema, applies and reverses on both Postgres and SQLite, and `scripts.bootstrap` runs
  it rather than `create_all`, so local and deployed schemas share one source of truth.
- ~~No jest tests (IAP-27)~~ — `npm test` runs 13 specs.
- ~~Postgres is untested~~ — the schema, seed, API, JSONB columns, version snapshot and
  restore, append-only audit trail and RBAC have all been exercised against Postgres 16,
  and CI runs the backend against a Postgres service container on every build.

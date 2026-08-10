# 2027 IAP Planning Module

A 2LOD assurance planning tool: turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios. Target platform is **FRAME**.

**FRAME is the deployment target, not a requirement to run it.** Locally the application
is self-contained: Python and Node, and nothing else. No FRAME, no Postgres, no Docker,
no identity provider, no network access at runtime. See
[Running without FRAME](#running-without-frame) for how identity works when the platform
is not in front of the API.

See [PLAN.md](PLAN.md) for the build plan, data model and settled decisions.

> **Just need the Helios CSV?** [`helios/`](helios/README.md) is a lite app that does only
> that — map approved reviews onto the Helios columns, normalise, validate, export. Standard
> library only, so `python3 -m helios` is the whole install story. It shares no code with the
> stack below and needs none of it running.

---

## Running it locally

You need **Python 3.12** and **Node 22**. That is the whole list — the database is a
SQLite file and authentication is stubbed, so there is nothing else to install, stand up
or connect to.

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
anyone who would rather run the steps by hand — **including on Windows, where `make` is
not present by default. See [On Windows](#on-windows).**

### Backend — http://127.0.0.1:8010

FRAME uses Poetry, so `poetry install && poetry run ...` is the canonical path, and
`poetry.lock` is committed so every machine resolves the same versions:

```bash
cd backend && poetry config virtualenvs.in-project true --local && poetry install
```

<details>
<summary><strong>"The currently activated Python version … is not supported by the project"</strong></summary>

Poetry found an interpreter older than 3.12, which is what `pyproject.toml` requires.
Install 3.12 and point Poetry at it rather than relaxing the constraint: the code uses
`datetime.UTC` and PEP 604 `X | None` annotations that Pydantic and SQLAlchemy evaluate
at runtime, so an older interpreter fails at import rather than degrading gracefully —
you would trade a clear error now for an obscure one at startup.

On Windows — `winget install Python.Python.3.12` if you do not have it, then ask the
launcher where it went and hand Poetry that path:

```powershell
py -3.12 -c "import sys; print(sys.executable)"
poetry env use C:\path\printed\above\python.exe
poetry install
```

On macOS or Linux, `python3.12` is usually already resolvable:

```bash
poetry env use python3.12
poetry install
```

`poetry env info --path` confirms which environment is now active. If it still complains,
delete `backend/.venv` and re-run — one may already exist built against the wrong
interpreter.

</details>

Create the local configuration. `auth_dev_mode` defaults to **false** so a deployment
that forgets to configure it fails closed with a 401 rather than accepting anonymous
callers as administrators — local development opts in through this file, which is
git-ignored:

```bash
cd backend && cp .env.example .env
```

<!-- Commands below use `poetry run`, which resolves the virtualenv the same way on every
platform. `.venv/bin/...` would be `.venv\Scripts\...` on Windows. -->

Create the schema and load the synthetic fixtures — 20 reviews ported from the
prototype. The schema comes from Alembic, the same migrations a deployed environment
runs, so a local database cannot drift from what SIT, UAT and PROD get. `--reset`
downgrades to base first, so re-run it any time to get back to a clean plan:

```bash
cd backend && poetry run python -m scripts.bootstrap --reset
```

Start it:

```bash
cd backend && poetry run python -m uvicorn app.main:app --port 8010 --reload
```

### Frontend — http://127.0.0.1:3010

```bash
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:3010**.

### On Windows

Everything runs natively — Python, Node, Poetry and npm all work, and the SQLite fallback
needs no extra services. Two things differ.

**`make` is not installed by default.** The `make` targets above are a convenience, not a
dependency; every one of them is a short command you can run directly. Either install it
(`winget install GnuWin32.Make`, or `scoop install make`) or use the commands below. Note
that even with `make` installed, `make clean` still won't work — it shells out to `find`
and `rm`. Under WSL or Git Bash the whole Makefile works unchanged.

**Virtualenv scripts live in `.venv\Scripts\`, not `.venv/bin/`.** Prefer `poetry run`,
which resolves this for you and is identical on every platform. The commands in this
README use it for that reason.

The full setup in PowerShell, from the repository root:

```powershell
# Backend
cd backend
poetry config virtualenvs.in-project true --local
poetry install
Copy-Item .env.example .env
poetry run python -m scripts.bootstrap --reset

# Frontend, in the same shell
cd ..\frontend
npm install
```

Then two terminals. Run the `cd` as its own line — do not chain it with `;`, which in
PowerShell runs the next statement whether or not the `cd` succeeded, and **the backend
must be started from `backend`** for the reason below:

```powershell
# Terminal 1 — from the repository root
cd backend
poetry run python -m uvicorn app.main:app --port 8010 --reload
```

```powershell
# Terminal 2 — from the repository root
cd frontend
npm run dev
```

In `cmd.exe` the only other change is `copy .env.example .env` for the setup step.

> `&&` chains only in PowerShell 7+. Windows PowerShell 5.1 — still the default on many
> machines — rejects it as a syntax error, and `;` is not a substitute because it ignores
> failure. Separate lines work in both.

<details>
<summary><strong>Started, but every request 401s or 500s</strong></summary>

Almost always the working directory. `poetry install` puts the project on the path, so
`app.main:app` imports from anywhere and **uvicorn starts happily** — `/health` even
returns 200. But two settings are resolved relative to the current directory, and neither
failure is loud:

- `.env` is read from the working directory, so outside `backend` it is not found,
  `IAP_AUTH_DEV_MODE` falls back to its secure default of false, and every request
  returns **401**.
- `IAP_DATABASE_URL` defaults to `sqlite+pysqlite:///./iap_local.db` — also relative — so
  a second, empty database file is created wherever you started from, and requests fail
  with **500** and `no such table: plan`.

`Get-Location` shows where you are; it must be the `backend` directory. A stray
zero-byte `iap_local.db` outside `backend` is the tell-tale sign, and is safe to delete.

</details>

**One PowerShell gotcha.** `curl` is an alias for `Invoke-WebRequest`, which does not take
`-H`. The RBAC example further down needs `curl.exe` explicitly:

```powershell
curl.exe -H "x-frame-user: someone" -H "x-frame-ad-groups: IAP_READER" http://127.0.0.1:8010/permission
```

Docker Desktop runs the containerised stack unchanged — `docker compose up --build`,
`docker compose run --rm seed`, `docker compose down -v`.

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

The script behind it is `frontend/scripts/generate-api.mjs`, which calls
openapi-typescript's API directly rather than shelling out. That is deliberate: the
previous one-line npm script defaulted the URL with `${NEXT_PUBLIC_API_BASE:-...}`, which
is POSIX shell syntax that `cmd.exe` passes through verbatim, so it fetched a literal
`${...}` and failed on Windows.

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

---

## Running without FRAME

In a deployed environment FRAME validates the AM Token and forwards the caller's identity
to the API as two headers, `x-frame-user` and `x-frame-ad-groups`. Locally there is no
FRAME to do that, so `IAP_AUTH_DEV_MODE=true` in `backend/.env` substitutes a synthetic
user holding all three roles. `make setup` writes that file for you, which is why the
application runs standalone with no further configuration.

RBAC is still real — dev mode supplies an identity, it does not bypass the checks. Send
the headers FRAME would and the roles apply exactly as they would in a deployment:

```bash
curl -H "x-frame-user: someone" -H "x-frame-ad-groups: IAP_READER" \
  http://127.0.0.1:8010/permission
```

A reader gets 403 on any write; a planner gets 201. The AD-group-to-role map is
`app/auth/frame.py`.

### Local development versus deploying without FRAME

These are different problems and only the first is solved by a setting.

**On your own machine**, dev mode is exactly right. It is what it exists for.

**Anything shared** — a team server, a demo box, anything reachable by another person —
must not use it. `IAP_AUTH_DEV_MODE=true` grants every caller planner, approver *and*
admin, with no authentication at all. It is not a weak default that could be tightened;
there is no credential in the exchange. It defaults to **false** so a deployment that
forgets to configure it fails closed with a 401 rather than silently admitting anonymous
administrators, and the server logs a warning on every start when it is on.

**To deploy without FRAME at all**, authentication has to be implemented. The seam is
clean: `app/auth/frame.py` is around 90 lines, and everything downstream depends only on
`get_current_user()` returning a `CurrentUser`. Putting OIDC or SAML against your own IdP
there, or a reverse proxy that authenticates and sets the same two headers, is a change to
that one file — no router, service or model touches auth. The AD group names would become
whatever your groups or claims are called.

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
| `IAP_AUTH_DEV_MODE` | **false.** With it on, any unauthenticated caller is granted planner, approver *and* admin. Deploying somewhere without FRAME means implementing auth, not enabling this — see [Running without FRAME](#running-without-frame) |
| `IAP_CORS_ORIGINS` | The deployed frontend origin. Never `*` — the API trusts role-bearing headers |

The API trusts `x-frame-user` and `x-frame-ad-groups` completely, so it must be
unreachable except through FRAME, and FRAME must **strip client-supplied `x-frame-*`
headers at the edge** rather than pass them through. Confirm that with the platform team:
it is the difference between correct and wide open.

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
| `frontend/scripts/generate-api.mjs` | The `generate:api` fallback URL points at localhost |
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

Without `make` — on Windows, or anywhere else:

```bash
cd backend  && poetry run pytest      # 35 cases
cd frontend && npm test               # 13 cases
```

The backend's 35 cases cover the methodology in `BUILD_INSTRUCTIONS.md` section 2. They
are written against the services layer, before the UI, so a later refactor cannot quietly
break the rules.

The frontend's 13 cases cover `errorMessage` — the API's rejection is what the user is
shown, so the UI never pre-empts a rule — and `usePlan`'s load, failure and resync paths.
They stub `fetch` at setup module scope, because openapi-fetch captures `globalThis.fetch`
when the client is constructed: a stub installed any later would leave the specs quietly
talking to a real backend.

If either reports `No module named pytest`, the dev dependencies were not installed —
run `poetry install` in `backend`.

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

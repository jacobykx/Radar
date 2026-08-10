# 2027 IAP Planning Module — Windows

A 2LOD assurance planning tool: turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios. Target platform is **FRAME**.

**This README is written for Windows.** Every command below is PowerShell, run from the
repository root unless a step says otherwise. The `Makefile` in this repository is for
POSIX shells only — see [Why not `make`](#why-not-make) — so the PowerShell commands here
are the supported local path on Windows, not a fallback.

**FRAME is the deployment target, not a requirement to run it.** Locally the application
is self-contained: Python and Node, and nothing else. No FRAME, no Postgres, no Docker,
no identity provider, no network access at runtime. See
[Running without FRAME](#running-without-frame) for how identity works when the platform
is not in front of the API.

See [PLAN.md](PLAN.md) for the build plan, data model and settled decisions.

---

## Prerequisites

| Need | Version | Install |
|---|---|---|
| Windows | 10 (1809+) or 11 | — |
| PowerShell | 7.x, or the built-in Windows PowerShell 5.1 | `winget install Microsoft.PowerShell` |
| Python | **3.12** | `winget install Python.Python.3.12` |
| Node.js | **22** | `winget install OpenJS.NodeJS.LTS` |
| Poetry | 1.8+ | `py -3.12 -m pip install --user poetry` |

That is the whole list — the database is a SQLite file and authentication is stubbed, so
there is nothing else to install, stand up or connect to. Docker Desktop is optional and
only needed for the [Postgres stack](#postgres-in-containers).

Close and reopen PowerShell after installing, so `python`, `node`, `npm` and `poetry` are
on `PATH`. Check with:

```powershell
python --version   # 3.12.x
node --version     # v22.x
poetry --version
```

If `python` opens the Microsoft Store instead of running, turn off the App Execution
Aliases for Python under **Settings → Apps → Advanced app settings → App execution
aliases**, or use `py -3.12` in place of `python` below.

---

## Running it locally

### One-time setup

```powershell
cd backend
poetry install
Copy-Item .env.example .env
cd ..\frontend
npm install
cd ..
```

`backend\poetry.toml` already pins the virtualenv in-project, so `poetry install` creates
`backend\.venv` with the interpreter at `backend\.venv\Scripts\python.exe`. Every command
below calls that executable by path, which means you never have to activate the
environment and never have to touch PowerShell's execution policy.

`.env` is git-ignored. `auth_dev_mode` defaults to **false** so a deployment that forgets
to configure it fails closed with a 401 rather than accepting anonymous callers as
administrators — local development opts in through this file.

### Create the schema and load the fixtures

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.bootstrap --reset
cd ..
```

This loads the 20 synthetic reviews ported from the prototype. The schema comes from
Alembic, the same migrations a deployed environment runs, so a local database cannot
drift from what SIT, UAT and PROD get. `--reset` downgrades to base first, so re-run it
any time to get back to a clean plan.

### Start both halves

Two PowerShell windows — or two tabs in Windows Terminal.

**Terminal 1 — backend, http://127.0.0.1:8010** (Swagger at `/docs`):

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010 --reload
```

**Terminal 2 — frontend, http://127.0.0.1:3010**:

```powershell
cd frontend
npm run dev
```

Then open **http://127.0.0.1:3010**.

If either port is already taken, find the owner and stop it:

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen | Select-Object OwningProcess
Stop-Process -Id <pid>
```

### Postgres, in containers

The SQLite fallback is convenient but it is not what gets deployed — it has no JSONB, no
concurrent writers and no transactional DDL. To develop against the real thing you need
**Docker Desktop for Windows with the WSL 2 backend** (Hyper-V or WSL 2 must be enabled;
Docker Desktop's installer walks through it):

```powershell
docker compose up --build          # Postgres + migrations + API + frontend
docker compose run --rm seed       # load the fixtures
docker compose down -v             # stop, and drop the volume
```

`docker compose` runs `alembic upgrade head` as its own `migrate` service and the API
waits for it to finish, so the service never starts against a schema older than its
code. Migrations are deliberately *not* run from the container entrypoint — a schema
change is a deploy step with its own approval, not a side effect of a container
starting.

To point the native setup at that Postgres instead of SQLite, set the environment
variable for the session before running anything:

```powershell
$env:IAP_DATABASE_URL = "postgresql+psycopg://iap:iap_local_dev@127.0.0.1:5432/iap"
cd backend
.venv\Scripts\python.exe -m scripts.bootstrap --reset
```

The variable lives only in that PowerShell session. To go back to SQLite, close the
window or clear it explicitly:

```powershell
Remove-Item Env:\IAP_DATABASE_URL
```

Do not set it to an empty string — an empty `IAP_DATABASE_URL` takes precedence over
`backend\.env` and leaves the application with no connection string.

### Migrations

```powershell
cd backend
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe revision --autogenerate -m "add widget table"
```

Autogenerate produces a **draft**: read it before committing. `alembic check` — which CI
runs — fails the build if a model was changed without a matching revision, so the two
cannot drift apart silently:

```powershell
cd backend
.venv\Scripts\alembic.exe check
```

### Regenerating the API client

`frontend\lib\api\generated\schema.d.ts` is generated from the backend's OpenAPI schema
and **is committed**, so the repo type-checks and builds without a running backend.
Never hand-write or hand-edit it — regenerate it whenever the API contract changes, with
the backend running.

**Do not use `npm run generate:api` on Windows.** That script uses POSIX shell parameter
expansion (`${NEXT_PUBLIC_API_BASE:-...}`), and npm runs scripts through `cmd.exe` on
Windows, which passes the string through literally and produces a bad URL. Call the
generator directly instead:

```powershell
cd frontend
npx openapi-typescript http://127.0.0.1:8010/openapi.json -o lib\api\generated\schema.d.ts
```

Substitute your own base URL if the backend is not on 8010. Regenerating is what turns a
backend contract change into a compile error rather than a runtime one, so run it before
assuming a frontend break is a frontend bug.

---

## Why not `make`

The repository ships a `Makefile`, and it is genuinely useful — on macOS and Linux. On
Windows it does not work, for three reasons that no amount of installing `make` fixes:

- every backend target hard-codes the POSIX virtualenv layout, `.venv/bin/python`, and a
  Windows virtualenv puts the interpreter at `.venv\Scripts\python.exe`;
- the recipes shell out to `cp`, `find` and `rm -rf`;
- `help` pipes through `grep` and `awk`.

Under Git Bash the second and third work and the first still does not. Rather than
maintain a second set of half-working targets, this README spells the commands out. The
mapping, if you are reading a `make` command from another document or a CI log:

| `make` target | PowerShell equivalent |
|---|---|
| `make setup` | `cd backend; poetry install; Copy-Item .env.example .env; cd ..\frontend; npm install` |
| `make dev-backend` | `cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --port 8010 --reload` |
| `make dev-frontend` | `cd frontend; npm run dev` |
| `make migrate` | `cd backend; .venv\Scripts\alembic.exe upgrade head` |
| `make migration M="…"` | `cd backend; .venv\Scripts\alembic.exe revision --autogenerate -m "…"` |
| `make seed` | `cd backend; .venv\Scripts\python.exe -m scripts.bootstrap` |
| `make reset` | `cd backend; .venv\Scripts\python.exe -m scripts.bootstrap --reset` |
| `make test-backend` | `cd backend; .venv\Scripts\python.exe -m pytest` |
| `make test-frontend` | `cd frontend; npm test` |
| `make lint` | `cd backend; .venv\Scripts\ruff.exe check .` |
| `make typecheck` | `cd frontend; npx tsc --noEmit` |
| `make build` | `cd frontend; npm run build` |
| `make generate-api` | `cd frontend; npx openapi-typescript http://127.0.0.1:8010/openapi.json -o lib\api\generated\schema.d.ts` |
| `make docker-up` / `-down` / `-seed` | `docker compose up --build` / `down -v` / `run --rm seed` |
| `make clean` | see [Cleaning up](#cleaning-up) |

---

## Windows-specific notes

**Long paths.** `node_modules` and `.next` nest deep enough to exceed the legacy 260-character
limit, which surfaces as `ENAMETOOLONG` or a truncated install. Enable long paths once, in
an **administrator** PowerShell, then reopen your shell:

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
git config --global core.longpaths true
```

Cloning close to the drive root (`C:\src\Radar` rather than a deep folder under
`Documents`) avoids most of this on its own.

**Antivirus.** Real-time scanning of `node_modules`, `.next` and `.venv` makes
`npm install` and `next dev` several times slower. If your organisation's policy allows
it, add the repository folder as a Microsoft Defender exclusion:

```powershell
Add-MpPreference -ExclusionPath "C:\src\Radar"   # administrator PowerShell
```

**Line endings.** The repository has no `.gitattributes`, so Git's default
`core.autocrlf=true` on Windows checks files out with CRLF. Python, TypeScript and the
tests are all indifferent to this, but it means a file touched on Windows and a file
touched on Linux can differ by line ending alone. If you see a whole-file diff with no
visible change, that is what happened — set `core.autocrlf=input` to stop producing them.

**Execution policy.** Nothing here needs `.venv\Scripts\Activate.ps1`, because every
command calls the interpreter by path. If you would rather activate the environment,
allow local scripts once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`curl` is not curl.** In PowerShell, `curl` is an alias for `Invoke-WebRequest` and
does not accept `-H`. Use `curl.exe` (shipped with Windows 10 1803 and later) or
`Invoke-RestMethod` — both forms appear in
[Running without FRAME](#running-without-frame).

**cmd.exe.** The commands here assume PowerShell. In `cmd.exe`, `;` is not a statement
separator (use `&&`), `$env:VAR = "x"` becomes `set VAR=x`, and `Copy-Item` /
`Remove-Item` become `copy` / `del`. PowerShell is the shorter road.

### Cleaning up

```powershell
Remove-Item -Recurse -Force backend\.venv, backend\.pytest_cache, backend\.ruff_cache `
  -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force frontend\node_modules, frontend\.next -ErrorAction SilentlyContinue
Get-ChildItem backend -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Remove-Item backend\*.db -ErrorAction SilentlyContinue
```

Everything removed here is regenerable: re-run the [one-time setup](#one-time-setup) and
the [fixtures](#create-the-schema-and-load-the-fixtures).

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
FRAME to do that, so `IAP_AUTH_DEV_MODE=true` in `backend\.env` substitutes a synthetic
user holding all three roles. The `Copy-Item .env.example .env` step in setup puts it
there, which is why the application runs standalone with no further configuration.

RBAC is still real — dev mode supplies an identity, it does not bypass the checks. Send
the headers FRAME would and the roles apply exactly as they would in a deployment:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/permission -Headers @{
    "x-frame-user"      = "someone"
    "x-frame-ad-groups" = "IAP_READER"
}
```

Or, if you prefer the curl form — note `curl.exe`, not `curl`, and the backtick line
continuation:

```powershell
curl.exe -H "x-frame-user: someone" -H "x-frame-ad-groups: IAP_READER" `
  http://127.0.0.1:8010/permission
```

A reader gets 403 on any write; a planner gets 201. `Invoke-RestMethod` raises a
terminating error on a 4xx rather than printing the body, so wrap it in `try`/`catch` — or
use `curl.exe` — when the failure is the thing you are testing. The AD-group-to-role map
is `app\auth\frame.py`.

### Local development versus deploying without FRAME

These are different problems and only the first is solved by a setting.

**On your own machine**, dev mode is exactly right. It is what it exists for.

**Anything shared** — a team server, a demo box, anything reachable by another person —
must not use it. `IAP_AUTH_DEV_MODE=true` grants every caller planner, approver *and*
admin, with no authentication at all. It is not a weak default that could be tightened;
there is no credential in the exchange. It defaults to **false** so a deployment that
forgets to configure it fails closed with a 401 rather than silently admitting anonymous
administrators, and the server logs a warning on every start when it is on.

That includes a Windows box on a corporate network: binding to `127.0.0.1`, as the
commands above do, is what keeps it local. Do not swap in `--host 0.0.0.0` and open a
firewall rule for it with dev mode on.

**To deploy without FRAME at all**, authentication has to be implemented. The seam is
clean: `app\auth\frame.py` is around 90 lines, and everything downstream depends only on
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

Note that the deployment target is Linux containers under FRAME regardless of what you
develop on. Windows is a development platform here, not a deployment one — which is why
the container images and CI both build on Linux.

### Configuration

`backend\.env.deployed.example` is the template for SIT, UAT and PROD. Its values belong
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
| `frontend\next.config.mjs` | `allowedDevOrigins` is a development-only workaround; `NEXT_PUBLIC_API_BASE` should come from environment configuration |
| `frontend\package.json` | The `generate:api` URL points at localhost, and its POSIX default-expansion syntax does not run under `cmd.exe` |
| `Jenkinsfile` | The agent label and credential IDs are placeholders, confirmed during FRAME onboarding |
| Branch names | FRAME's Jenkins triggers on `feature/all/<JIRA-TICKET>` |

`NEXT_PUBLIC_API_BASE` is inlined into the client bundle at build time, so a different
backend URL means a different frontend image — pass it as a build argument, not a
runtime variable.

---

## CI

`.github/workflows/ci.yml` runs on GitHub; `Jenkinsfile` describes the same stages for
FRAME. **Both run on Linux**, so a Windows-only problem — a path separator, a CRLF-sensitive
fixture, a case-insensitive filename collision — will not be caught there. Run the checks
locally before pushing. Both pipelines run:

| Check | Catches |
|---|---|
| `ruff check` | Lint |
| `pytest` | The 35 methodology cases |
| `alembic upgrade` → `downgrade` → `upgrade` | A migration that is not reversible |
| `alembic check` | A model changed without a matching revision |
| `tsc --noEmit`, `jest`, `next build` | Frontend type, logic and build breaks |
| `openapi-typescript` + `git diff --exit-code` | A committed API client that has gone stale against the backend |

The backend job runs against a Postgres 16 service container, not the SQLite fallback,
so dialect-specific problems fail in CI rather than in an environment.

The same set, locally:

```powershell
cd backend
.venv\Scripts\ruff.exe check .
.venv\Scripts\python.exe -m pytest
cd ..\frontend
npx tsc --noEmit
npm test
npm run build
```

Case matters here in a way it does not on Windows: NTFS is case-insensitive, so an import
of `./components/Foo` that should read `./components/foo` resolves happily on your machine
and fails the Linux build. If CI reports a module that "cannot be found" but plainly
exists, check the casing first.

---

## Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest      # 35 cases

cd ..\frontend
npm test                                # jest — 13 cases
```

The backend's 35 cases cover the methodology in `BUILD_INSTRUCTIONS.md` section 2. They
are written against the services layer, before the UI, so a later refactor cannot quietly
break the rules.

The frontend's 13 cases cover `errorMessage` — the API's rejection is what the user is
shown, so the UI never pre-empts a rule — and `usePlan`'s load, failure and resync paths.
They stub `fetch` at setup module scope, because openapi-fetch captures `globalThis.fetch`
when the client is constructed: a stub installed any later would leave the specs quietly
talking to a real backend.

If pytest reports `No module named pytest`, the dev dependencies were not installed — run
`poetry install` in `backend` again. If it reports that `.venv\Scripts\python.exe` does not
exist, the virtualenv was never created: check that `poetry install` ran from inside
`backend`, where `poetry.toml` pins it in-project.

---

## Known gaps

- **Integrations are stubs**: the scoring engine, RCA/RRIS linkage and the Helios KBD
  reference-data feed are seeded as synthetic data. `reference.fetch_from_kbd()` is the
  seam where the real feed lands (IAP-22, IAP-24, IAP-25).
- **The Phase 2 GenAI tab is not ported** — roadmap content, no behaviour.
- **The container images have not been built.** The Dockerfiles and `docker-compose.yml`
  are written and the compose file validates, but the machine they were authored on had
  no Docker daemon, so `docker compose up --build` is unproven — on Docker Desktop for
  Windows as much as anywhere else.
- **The Jenkins job itself is not configured.** `Jenkinsfile` describes the stages; the
  job, agent labels and credential IDs come from FRAME onboarding.
- **Frontend coverage is thin.** The specs cover `lib\`; the six stage components are
  currently exercised only through the API contract and the production build.
- **No Windows task runner.** The `Makefile` is POSIX-only and there is no `make.ps1`
  beside it, so the PowerShell commands in this README are typed by hand rather than
  wrapped. A PowerShell script mirroring the targets would remove that.
- **CI does not run on Windows.** Neither pipeline has a Windows runner, so Windows-only
  regressions are found by developers, not by the build.

### Closed since the first cut

- ~~Alembic migrations (IAP-3)~~ — an initial revision now generates the full 15-table
  schema, applies and reverses on both Postgres and SQLite, and `scripts.bootstrap` runs
  it rather than `create_all`, so local and deployed schemas share one source of truth.
- ~~No jest tests (IAP-27)~~ — `npm test` runs 13 specs.
- ~~Postgres is untested~~ — the schema, seed, API, JSONB columns, version snapshot and
  restore, append-only audit trail and RBAC have all been exercised against Postgres 16,
  and CI runs the backend against a Postgres service container on every build.

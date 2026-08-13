# 2027 IAP Planning Module

A 2LOD assurance planning tool: turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios.

For the POC it runs as a **static site** — the workflow executes in the browser and the
plan is a JSON document served alongside it. That makes hosting it a matter of copying a
folder onto IIS; see [Hosting on Windows](#hosting-on-windows).

See [PLAN.md](PLAN.md) for the build plan, data model and settled decisions.

---

## How this POC is put together

The workflow runs **in the UI**, the way the HTML prototype does, and the plan it works
on is a **JSON instance document**. There is no database and no backend process in the
loop:

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
| Identity and roles | carried in the instance document | authentication gateway (IIS Windows Authentication, a reverse proxy, or SSO) |
| Concurrency | `row_version` checked locally; one user | 409 against a shared database |
| Persistence | `localStorage`, plus export/import of the JSON | Postgres |

Client-side role checks demonstrate the rule, they do not secure it — anything running
in a browser can be edited by the person running it. That is the reason the rules also
exist in `backend/app/domain`, and the reason both copies are covered by tests.

---

## Running it on a Windows laptop

### 1. Install Node.js (once)

Download the **LTS** installer from [nodejs.org](https://nodejs.org/) and accept the
defaults. Then **open a new PowerShell window** — an already-open one will not have
Node on its PATH — and check it:

```powershell
node -v      # v20.x or later
npm -v
```

### 2. Get the code

Either clone it:

```powershell
cd $HOME\Documents
git clone https://github.com/jacobykx/Radar.git
```

or, without Git: **Code → Download ZIP** on GitHub, then right-click the file →
**Extract All**. Windows blocks files from the internet until they are unblocked, so if
anything behaves oddly, right-click the ZIP → Properties → tick **Unblock** before
extracting.

### 3. Run it

From the folder you just created — the one containing `README.md`, `frontend` and
`backend`:

```powershell
cd $HOME\Documents\Radar
npm install
npm run dev
```

`npm install` takes a couple of minutes the first time and prints a lot; that is
normal. When it finishes, `npm run dev` prints `Ready in …`. Open
**http://127.0.0.1:3010** in your browser.

Stop it with `Ctrl+C`. Next time, only `npm run dev` is needed.

> The commands above run from the **repository root** — `package.json` there forwards
> them to `frontend`. Running them inside `frontend` works too; nothing else does.

### If something goes wrong

| What you see | What it means |
|---|---|
| `npm error enoent Could not read package.json` | You are in the wrong folder. `dir` should list `frontend`, `backend` and `README.md`; if it does not, `cd` to the folder that does. Extracting a ZIP often nests it — `Radar\Radar\…` — so you may need to `cd Radar` once more. |
| `npm : File …\npm.ps1 cannot be loaded because running scripts is disabled` | PowerShell's execution policy. Either use **Command Prompt** instead, or run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` in PowerShell and answer `Y`. |
| `'npm' is not recognized` | Node is not installed, or the window was open before you installed it. Close it, open a new one, and check `node -v`. |
| `EADDRINUSE … 3010`, or Next.js says a server is already running | Something already holds the port — most often a previous `npm run dev` you did not stop. Close that window, or start on another port with `cd frontend` then `npx next dev -p 3011`, and open **http://127.0.0.1:3011**. |
| The page loads but says it cannot load the instance | `frontend\public\instances\2027-iap.json` is missing or the ZIP extracted incompletely. Re-extract, or regenerate it (see below). |

Corporate laptops sometimes route npm through an internal registry. If `npm install`
cannot reach the network, ask IT for the registry URL and set it once with
`npm config set registry <url>`.

### Pointing at a different plan

The instance loads from `/instances/2027-iap.json`. To use another one, set
`NEXT_PUBLIC_INSTANCE_URL` before starting:

```powershell
$env:NEXT_PUBLIC_INSTANCE_URL = "http://intranet/plans/2027-draft.json"
npm run dev
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

```powershell
cd backend
py -m scripts.export_instance
cd ..
```

No dependencies, no database — `app/seed/data.py` is plain Python. Edit the fixtures
there and re-run, or hand-edit the JSON for a one-off scenario.

---

## Hosting on Windows

### As a static site on IIS (recommended for the POC)

The POC does no server-side work, so it exports to a folder of files:

```powershell
npm install
npm run build:static
```

That writes `frontend\out`. Copy its contents to the site's physical path — for example
`C:\inetpub\wwwroot\iap` — and point an IIS site or application at it. No Node runtime
and no application pool identity are needed on the server; it is static content.

`public\web.config` is copied into the export, so the folder arrives already
configured: `index.html` as the default document, a MIME mapping for `.json`, and
caching disabled for `/instances` so a re-hosted plan is picked up on the next reload
rather than after a cache expiry.

**Serving under a sub-path.** An IIS *application* under a site (`https://host/iap`)
needs the app built for that path, because the asset URLs are baked in at build time:

```powershell
$env:NEXT_BASE_PATH = "/iap"
npm run build:static
```

The default instance URL follows `NEXT_BASE_PATH`, so `/iap/instances/2027-iap.json` is
what the page requests. A site at the root needs no `NEXT_BASE_PATH`.

**Swapping the plan without redeploying.** Overwrite
`<site>\instances\2027-iap.json` with an exported instance. Nothing else changes — the
UI reads it on the next load. Keep the previous file if you want to roll back.

### Under Node (IIS reverse proxy, a Windows service, or a container)

If you would rather run the Next.js server — for example to serve it behind IIS with
ARR, or to add server-side pieces later:

```powershell
npm install
npm run build
npm start          # http://127.0.0.1:3010
```

To keep it running across reboots, register it as a Windows service with a supervisor
such as [NSSM](https://nssm.cc/) or `sc.exe`, pointing at `node` with
`node_modules\next\dist\bin\next start -p 3010` as the arguments and `frontend` as the
working directory. Front it with IIS + Application Request Routing if it needs to sit
under an existing host name.

### Identity on a Windows host

The POC takes its identity from the `identity` block of the instance document, so
"who am I" is whatever that file says. To make it real, put the app behind IIS with
Windows Authentication and run the backend, which reads `x-auth-user` and
`x-auth-groups` from the gateway and maps AD groups to roles
(`backend/app/auth/gateway.py`). Those header names are the contract between the two —
change them in one place if your gateway sends different ones.

---

## What to try

| Stage | Worth exercising |
|---|---|
| **Add a review** | Two forms at the top of Risk Radar. *Regulatory Assurance* files a mandated review: it is pinned into the plan and, given a go-live date, into that date's quarter, routes to IRR at sign-off, and links to any other review sharing its RRIS ID. *Risk Assurance* files a risk-led candidate into the backlog. Both refuse to save without a rationale, and neither asks for factor scores — those are the scoring engine's. |
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

```powershell
npm test          # 66 cases — the engine
npm run typecheck
```

`__tests__/domain-rules.test.ts` mirrors `backend/tests/test_domain_rules.py` case for
case; `__tests__/workflow.test.ts` covers the refusals, the audit trail and version
restore; `__tests__/instance.test.ts` covers loading a hosted document, including the
shipped one.

The backend suite still runs unchanged:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\pip install pytest ruff
.venv\Scripts\python -m pytest        # 35 cases — the services layer
```

---

## Running the backend (unchanged, not required for the POC)

Nothing in the UI calls it, but it is still the deployment target and still runs:

```powershell
cd backend
copy .env.example .env
.venv\Scripts\python -m scripts.bootstrap --reset
.venv\Scripts\python -m uvicorn app.main:app --port 8010 --reload
```

Swagger at [/docs](http://127.0.0.1:8010/docs). `IAP_AUTH_DEV_MODE` supplies a synthetic
user locally and **must stay false in every deployed environment** — with it on, any
unauthenticated caller is granted every role. It defaults to false and the server logs a
warning on every start when it is on.

---

## Moving this into another repository

The tracked files are the whole deliverable — no secrets. Everything regenerable is
git-ignored: virtualenvs, `node_modules`, `.next`, `out`, the SQLite database.

```powershell
git remote add origin <new-repo-url>
git push -u origin <branch>
```

### Change on arrival

| Where | Why |
|---|---|
| `NEXT_PUBLIC_INSTANCE_URL` | Points at the hosted instance for that environment |
| `NEXT_BASE_PATH` | Set when the site is served under a sub-path, before building |
| `backend\.env` per environment | `IAP_DATABASE_URL` to Postgres, `IAP_AUTH_DEV_MODE=false`, `IAP_CORS_ORIGINS` |
| Ports **8010** / **3010** | Local choices only — 8000 and 3000 were in use on the development machine |
| `frontend\next.config.mjs` | `allowedDevOrigins` is a development-only workaround |
| `USER_HEADER` / `GROUPS_HEADER` in `backend\app\auth\gateway.py` | If the gateway forwards different header names |

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

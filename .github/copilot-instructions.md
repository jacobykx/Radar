# Copilot instructions — 2027 IAP Planning Module

A 2LOD assurance planning tool. It turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual assurance plan, exported
to Helios. Target platform is **FRAME**.

`README.md` is how to run it. `PLAN.md` is the build plan, the data model and the settled
decisions — every behaviour is traced to a line in the original prototype, so when a rule
is unclear, check there before inventing one.

## Layout

```
backend/    Poetry · FastAPI · SQLAlchemy · Alembic · Pydantic
  app/api/         routers — thin: parse, call a service, serialise
  app/services/    ALL domain logic (priority, capacity, waterfall, routing, descope,
                   snapshot/restore). Pure functions over loaded state
  app/domain/      methodology constants and pure calculations
  app/models/      SQLAlchemy ORM
  app/schemas/     Pydantic in/out — read-only fields enforced here
  app/auth/        FRAME header → (username, ad_groups). No login, no sessions, no tokens
  app/migrations/  Alembic. Every revision reversible
  tests/           pytest, against the services layer
frontend/   Next.js · TypeScript
  lib/api/generated/  GENERATED from the OpenAPI schema — never hand-edited
```

## Commands

```bash
make setup     # Poetry + npm install, writes backend/.env
make reset     # migrate to head, load the 20 synthetic reviews
make check     # lint, typecheck, both test suites, build — what CI runs
make help      # everything else
```

## Architecture rules

These are settled decisions, not preferences. Do not work around them.

- **Every rule is enforced server-side.** The frontend renders and calls; it never
  decides. If a rule needs to exist in the UI, it belongs in a service first.
- **Domain logic goes in `app/services/`, never in a router.** Routers parse, delegate
  and serialise. Services take loaded state and return values, so they stay unit-testable
  without HTTP.
- **No hand-rolled auth.** FRAME terminates authentication and forwards user context in
  headers. Do not add login endpoints, sessions, tokens or password handling.
- **The UI shows the API's rejection message.** A methodology violation returns
  `{detail, rule}` and a 4xx; the frontend surfaces `detail` via `errorMessage()` rather
  than pre-empting the rule with its own copy.
- **No `alert` / `prompt` / `confirm`.** Rationale is captured inline.
- **`frontend/lib/api/generated/schema.d.ts` is generated and committed.** Never edit it
  by hand. Regenerate with `npm run generate:api` when the API contract changes — CI
  fails the build if it has drifted.

## Domain invariants

Breaking one of these is a methodology bug, not a style issue.

- **The audit trail is append-only.** One write path, no update and no delete endpoint;
  `DELETE /audit` returns 405. Restoring a version is itself an audited event, and audit
  entries are never rolled back or included in a snapshot.
- **The computed priority is never overwritten.** An override is stored separately and
  requires a rationale; the computed value survives beside it.
- **Mandated reviews carry the label `Mandated`, not a numeric priority.**
- **The waterfall never over-fills.** Reviews are placed in the earliest quarter where
  `load + fte <= capacity`, mandated first, then by effective priority descending.
  Anything that does not fit is reported as unplaced — never absorbed, never spilled into
  a quarter that lacks the capacity.
- **A descoped review is excluded everywhere downstream** — staging totals, capacity,
  approval scope, pre-staging and the plan. It is greyed in Risk Radar, not deleted.
- **One approval gate per review**, routed IRR if mandated, else RCA if RCA-linked, else
  Standard. Approving needs no comment; **returning requires one**.
- **Plan and IAP quarter/year are derived** from Target Start Date and must not be typed.

## Database

Postgres in every deployed environment; SQLite is a local-development fallback only.

- **Schema changes need an Alembic revision.** `alembic check` runs in CI and fails the
  build if a model changed without one. Never reach for `Base.metadata.create_all` —
  `scripts.bootstrap` runs the migration so local and deployed schemas cannot diverge.
- **Autogenerate produces a draft.** Read it before committing.
- **Keep migrations dialect-agnostic.** Use `sa.func.now()` for a timestamp default, not
  `sa.text("now()")` — the latter is valid Postgres and breaks SQLite outright.
- **Reversible.** CI applies, reverses and re-applies every revision.
- JSONB on Postgres degrades to plain JSON on SQLite via `JSONType` in `models/base.py`.

## Configuration and security

- **`IAP_AUTH_DEV_MODE` must be false everywhere but a developer's machine.** With it on,
  any unauthenticated caller is granted planner, approver *and* admin. It defaults to
  false so a misconfigured deployment fails closed with a 401.
- **`IAP_CORS_ORIGINS` is never `*`.** The API trusts role-bearing headers, so a
  permissive origin is an authorisation problem, not just a CORS one.
- **No connection string, credential or token in the repository.** `backend/.env` is
  git-ignored; `.env.example` and `.env.deployed.example` carry placeholders only.
- `NEXT_PUBLIC_API_BASE` is inlined into the client bundle at build time, so a different
  backend URL means a different frontend image — pass it as a build argument.

## Conventions

- Python: ruff, line length 100, `select = ["E", "F", "I", "UP", "B", "SIM"]`. FastAPI's
  `Depends()` in a parameter default is allowed through `extend-immutable-calls` — do not
  add `# noqa: B008`.
- Comments explain *why*, and cite the rule or decision they implement. Do not narrate
  what the code already says.
- Tests are written against the services layer before the UI, so a later refactor cannot
  quietly break a methodology rule.

## Two traps

- **jest specs must stub `fetch` at setup module scope.** openapi-fetch captures
  `globalThis.fetch` when the client is constructed, which happens on import — a stub
  installed in `beforeEach` is too late and leaves specs silently hitting a real backend.
- **`alembic check` gives false positives on SQLite** for server defaults, because SQLite
  reflects `CURRENT_TIMESTAMP` as text that never matches `func.now()`. The comparison is
  deliberately scoped to Postgres in `app/migrations/env.py`.

## Known stubs

The scoring engine, RCA/RRIS linkage and the Helios KBD reference-data feed are synthetic
seed data. `reference.fetch_from_kbd()` is the seam where the real feed lands. Do not
build on the seed values as though they were live reference data.

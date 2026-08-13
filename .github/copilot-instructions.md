# Working on this repository

GitHub Copilot reads this file automatically for every request made in this workspace.
It is the shortest complete briefing on what this codebase is and what must not be
broken. Keep it accurate — if a change here makes a statement below untrue, update it in
the same commit.

## What this is

A 2LOD assurance planning tool. It turns risk-scoring output and externally-mandated
obligations into a shaped, capacity-feasible, signed-off annual plan, exported to Helios.

For the POC **the workflow runs in the browser** and the plan is a **JSON instance
document** served as a static file. There is no database and no backend in the loop.

```
frontend/public/instances/2027-iap.json   the instance: reference data, capacity,
                                          20 candidate reviews, plan state
frontend/lib/engine/                      the workflow (see below)
frontend/lib/usePlan.ts                   loads the instance, runs commands, persists
frontend/components/                      screens: render and call, never decide
backend/                                  FastAPI service — the productionisation
                                          target, not called by the POC
```

## The engine

`frontend/lib/engine/` is the whole methodology, split by concern:

| File | Holds |
|---|---|
| `constants.ts` | quarters, sizes, FTE, bands, routes, roles |
| `types.ts` | the instance document's shape |
| `scoring.ts` | weighted priority, bands, overrides |
| `capacity.ts` | FTE demand, headroom, bottom-up fill |
| `scheduling.ts` | the Q1→Q4 waterfall |
| `staging.ts` | staging, descoping, origin rules |
| `approval.ts` | routes, gates, cross-team linkage |
| `helios.ts` | the pre-staging field spec and derived fields |
| `select.ts` | read models — every screen reads through here |
| `workflow.ts` | **commands** — every change a user can make |
| `instance.ts` | loading and normalising the hosted JSON |
| `storage.ts` | the `localStorage` working copy |
| `csv.ts` | exports |

**Commands are pure.** A command takes the instance document, applies the rules, and
returns a *new* document. It never mutates its input, never touches React, `fetch` or
`localStorage`. Two invariants hold for every one of them:

1. a rule violation throws a `DomainError` (or a subclass) and the document is unchanged;
2. a successful change appends to the audit trail in the same step.

Screens read through `select.ts` and write through `plan.run(...)` from `usePlan`.
A component must never edit the document itself.

## Rules that must not be broken

These are assurance-methodology facts, not preferences. Each is covered by a test.

1. **Factor scores are read-only.** Risk, urgency, coverage gap and change come from the
   scoring engine. No form, command or screen may edit them.
2. **Priority = (a·risk + b·urgency + c·coverage + d·change) ÷ (a+b+c+d)**, so it stays on
   the 1–5 scale whatever the weights. All-zero weights must not divide by zero.
3. **An override needs a rationale**, and never overwrites the computed value — both are
   stored and both stay visible.
4. **Mandated ⇒ origin "Regulatory Assurance"**, and only mandated reviews use it.
5. **Mandated reviews are not driver-scored.** They show `Mandated`, no number.
6. **Descoping needs a rationale**, and a descoped review leaves staging, capacity,
   approval, pre-staging and the plan. It is greyed, never deleted.
7. **Sizes S/M/L = 60/90/120 days and 2/3/4 FTE**; a per-review FTE override wins.
8. **Capacity is FTE per quarter per assurance function.** One function's spare capacity
   never covers another's.
9. **Auto-fill is a waterfall**: earliest quarter with room, mandated first then by
   priority, never over-filling. What will not fit is reported, not absorbed.
10. **One sign-off gate per review**, routed IRR (mandated) / RCA (RCA-linked) /
    Standard. Approving needs no comment; **returning does**.
11. **The audit trail is append-only.** There is no command that edits or removes an
    entry, and a test asserts that against the command list.
12. **Version restore** puts back plan state, never the audit trail — restoring is itself
    an audited event.
13. **A review may span locations.** A location filter matches if any location matches.
14. **Helios plan/IAP quarter and year are derived** from Target Start Date, never typed.
15. **No `alert`, `prompt` or `confirm`.** Rationale and confirmation are captured inline.

## The rules exist twice

`frontend/lib/engine/` (TypeScript) and `backend/app/domain/` (Python) state the same
methodology. **Change one and you must change the other**, plus both test suites:

- `frontend/__tests__/domain-rules.test.ts` mirrors `backend/tests/test_domain_rules.py`
  case for case
- `frontend/__tests__/workflow.test.ts` covers refusals, the audit trail, version restore
- `frontend/__tests__/instance.test.ts` covers loading a hosted document
- `frontend/__tests__/conventions.test.ts` asserts rules 1, 11 and 15 — the ones that are
  not calculations, and so the ones a plausible-looking change breaks quietly

If a change only makes sense in one of them, say so in the commit message.

## Conventions

- **snake_case** for anything in the instance document, matching the API's field names,
  so the same document could later be served by the backend. camelCase only for Helios
  field keys, which come from the Helios spec.
- **Comments explain why, not what.** Match the density around you; trace methodology to
  its rule number.
- **Types over casts.** No `any`; no `as` to silence the compiler.
- The fixtures live in `backend/app/seed/data.py` and are exported to the instance JSON by
  `backend/scripts/export_instance.py`. **Never hand-edit
  `frontend/public/instances/2027-iap.json` if the change belongs in the fixtures** —
  edit the seed and re-run the script, or the two drift.

## Verifying a change

From the repository root:

```powershell
npm test          # 70 engine cases
npm run typecheck # TypeScript
npm run dev       # then look at it in a browser
```

If the backend was touched:

```powershell
cd backend
.venv\Scripts\python -m pytest
cd ..
```

A change is not finished until the tests that cover it pass and, for anything visible,
you have seen it work in the browser.

## Out of scope for the POC

- Server-side enforcement, real identity, multi-user concurrency — deliberate; see the
  README's "What the POC gives up".
- Alembic migrations, component tests, the Phase 2 GenAI tab.

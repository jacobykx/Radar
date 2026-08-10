# IAP Planning Module

The planning workflow from the MVP prototype (`2027_IAP_Planning_Module.html`), rebuilt as
a real application, ending in a **valid Helios bulk upload CSV**.

Candidate reviews are scored, weighted and staged; the plan is fitted to FTE capacity and
phased across quarters; each review passes one sign-off gate; then the Helios attributes
are captured and exported. Every decision along the way is written to an audit trail.

Standard library only — no pip install, no Poetry, no Node, no database. **Python 3.12**,
the same interpreter `backend/` requires, so one machine setup runs the whole repository.

```bash
python3 -m helios                          # the planning module on http://127.0.0.1:8000
python3 -m helios --data plans/2027.json   # keep the plan somewhere else
python3 -m helios reviews.csv -o out.csv   # convert a CSV without opening a browser at all
python3 -m unittest discover -s helios/tests -t .
```

Or `make helios` / `make test-helios` from the repository root.

On **Windows**, use the launcher and run from the repository root — there is nothing to
install and `make` is not needed:

```powershell
py -m helios
py -m helios reviews.csv -o out.csv
py -m unittest discover -s helios\tests -t .
```

CI runs the full suite on `windows-latest` as well as Linux, so "works on Windows" is a
test result rather than an intention. See [Windows specifics](#windows-specifics) for what
that covers.

## The nine screens

Risk Radar · Staging & capacity · Shaped plan · Approval · Pre-staging (Helios) ·
Versions · Audit trail · Reference data · Phase 2 GenAI roadmap.

## How it is laid out

The export half — everything that turns a review into a Helios row:

| Module | Responsibility |
| --- | --- |
| `spec.py` | The 27 Helios columns, their allowed values, the required set, the derived fields |
| `reference.py` | Reference data, and normalisation onto canonical spellings |
| `mapping.py` | Approved reviews → Helios columns |
| `validation.py` | Required fields and allowed values, with explicit per-row errors |
| `export.py` | The CSV itself |

The planning half — everything upstream of it, in `planning/`:

| Module | Responsibility | Rules |
| --- | --- | --- |
| `scoring.py` | Weighted priority, overrides, bands | 2, 3, 5 |
| `staging.py` | Staging and descoping | 4, 6 |
| `capacity.py` | FTE demand against per-quarter capacity | 7, 8 |
| `scheduling.py` | Waterfall Q1 → Q4 auto-fill | 9 |
| `approval.py` | Routes, gates and sign-off | 10 |
| `store.py` | The plan on disk, the audit trail, versions | 11 |
| `actions.py` | Every mutation, each one audited | |
| `views.py` | The JSON the screens render | |

`server.py` is a thin HTTP layer over both halves and holds no rules of its own, so the
file the browser downloads is byte-identical to the one the CLI writes. `views.py` computes
every derived number the UI shows, so no rule is implemented twice.

**SME-level resource allocation is deliberately absent.** The prototype's help text
describes it, but its tabs implement FTE capacity only, and `PLAN.md` records the machinery
as dropped. The tabs won.

## The pipeline

```
candidates ─▶ score & weight ─▶ stage ─▶ fit to capacity ─▶ phase ─▶ sign off ─▶ enrich ─▶ CSV
              (read-only        (rule 6   (rules 7, 8)     (rule 9)  (rule 10)   (Helios)
               facts, your       needs a
               weights)          reason)
```

### The rules worth knowing

**Priority is normalised.** `(a·risk + b·urgency + c·coverage_gap + d·change) ÷ (a+b+c+d)`,
so it stays on the 1–5 scale whatever the weights. The four scores are read-only facts from
a separate scoring engine; the weights are the planner's only lever.

**Mandated reviews are pinned.** They are not driver-scored, cannot be descoped, and hold
the quarter their go-live date implies — the scheduler works around them.

**Nothing leaves the plan silently.** Descoping needs a rationale, an override needs a
rationale, returning a review at its gate needs a comment. A refused change writes no audit
line, because it did not happen.

**Capacity is FTE per quarter per function.** S/M/L needs 2/3/4 FTE unless overridden.
Mandated demand commits first; the waterfall packs the earliest quarter with room and
leaves what cannot fit unscheduled and flagged rather than squeezing it in.

## The plan file

One JSON document — reviews, weights, capacities, reference data, the audit trail and saved
versions — written atomically (temp file, then `os.replace`, which is atomic on Windows
too). The prototype used `localStorage`, which means the audit trail dies with the browser
profile; a file survives, diffs in a review, and lets the CLI export exactly what the UI
shows. `--data` chooses where it lives; delete it to start again.

**Mapping.** A review arrives with whatever the planning side calls things — `ref`,
`team`, `sub-team`, `go-live`, `rationale` — and comes out on Helios columns. Seed defaults
(`Review Type`, `Assurance Review Status`, `Risk Flags`, `ESG Flag`) fill columns the source
never named; they never overwrite a column the source named and left blank, which is what
lets an exported file be re-imported unchanged.

**Normalisation.** Matching ignores case, spacing and dash style, so `cib - global banking`
resolves to `CIB — Global Banking`, and a handful of aliases resolve too (`United Kingdom`
→ `UK`, `HK` → `Hong Kong`). Dates are accepted as `YYYY-MM-DD`, `DD/MM/YYYY`, `18 Mar 2027`
or `Mar 2027`. Plan/IAP quarter and year are always recomputed from the Target Start Date —
a supplied value is discarded, never trusted.

A value that still does not resolve is **kept, not blanked**, and reported. It cannot reach
the CSV, and leaving it in place is the only way the person fixing it can see what to fix.

**Validation.** Every problem carries a row number, the column label and what to do:

```
row 2: Assurance Function: 'Made Up Assurance' is not a recognised value.
       Did you mean 'Financial Crime Assurance'?
row 2: Target Start Date: 'next spring' is not a date.
       Use YYYY-MM-DD, DD/MM/YYYY, '18 Mar 2027' or 'Mar 2027'.
```

**Export is all or nothing.** One bad row and no file is produced. A partially valid upload
is worse than none: Helios takes the good rows, and the rejected ones then go missing from
the plan with nothing on screen to say so.

## The CSV

27 columns in spec order, header row of Helios labels, every field quoted, CRLF line
endings, UTF-8. Add `?bom=1` to the export request for a byte-order mark if the file is
going to be opened in Excel first — the em dashes in the business names need it there, and
Helios's own loader is happier without it.

## Required fields

The Planning Key Fields spec requires: Review Type, Review Category, Assurance Function,
Review Lead, Review Team, Target Start Date, Review Scope and Rationale.

This app also requires **Lookup Key (Review ID)** and **Title**. The spec leaves them
implicit because the planning tool always populates them, but Helios keys the upload on the
lookup key, so a row without one cannot land. This is the one place the app is stricter than
the written spec — if that turns out to be wrong, remove them from `spec.REQUIRED`.

## HTTP API

The plan:

| | |
| --- | --- |
| `GET /` | the single-page UI |
| `GET /api/plan` | the whole plan, with every derived value the screens show |
| `POST /api/op/<name>` | one named mutation, then the whole plan again |
| `GET /api/prestaging/<ref>` | one review's Helios row: values and per-field errors |
| `GET /api/export/<what>` | `helios` · `plan` · `approvals` · `audit` → a CSV download |
| `POST /api/reset` | back to the seeded candidate list |

Every mutation goes through a named op, so nothing can change the plan without an audit
line. A refusal comes back `422` with the message shown verbatim to the planner.

And the stateless CSV endpoints, which need no plan file at all:

| | |
| --- | --- |
| `GET /api/spec` | columns, allowed values, reference lists, a blank row |
| `POST /api/import` | `{"csv": "..."}` or `{"reviews": [...]}` → mapped rows + errors |
| `POST /api/validate` | `{"rows": [...]}` → normalised rows + errors |
| `POST /api/export` | `{"rows": [...]}` → the CSV, or `422` with the errors that stopped it |

The UI holds no rules of its own — every check is the server's, so what is on screen is
what the export will enforce.

## Windows specifics

Three things go wrong on Windows and nowhere else. All three are fixed and covered by
tests that run on the Windows CI runner.

**Excel does not save UTF-8 by default.** "CSV (Comma delimited)" — the top entry in the
Save As dialog — writes cp1252. Reading that as UTF-8 aborts on the first em dash, and the
business names are full of them. Input is decoded as UTF-8 (BOM tolerated) and falls back
to cp1252, so a file straight out of Excel converts with no ceremony. Excel's other option,
"CSV UTF-8", writes a BOM; that is stripped.

**A redirected stdout takes the console code page.** `py -m helios plan.csv > out.csv` used
to produce a cp1252 file that Helios reads as mojibake, silently. The CSV is now written to
stdout as UTF-8 bytes, so it is the same file however it is redirected. `-o` was always
correct; the pipe was not.

**Line endings get translated twice.** The writer already emits CRLF, and Windows text mode
would turn each one into `\r\r\n`. The output file is opened with `newline=""` to stop that.

One case is only mitigated, not fixed: the browser's **file picker** always decodes as
UTF-8, so a cp1252 file loaded there arrives with replacement characters and the app cannot
tell what it should have been. It detects them and says to re-save as "CSV UTF-8" rather
than leaving you to work out why every business name is suddenly unrecognised. Pasting the
text in, or using the CLI, avoids it entirely.

Error messages contain em dashes and ellipses. On an older console code page that cannot
encode them they degrade to `?` rather than raising — a crash while reporting an error is
the worst time to have one.

## Reference data

The business, location and taxonomy lists are editable in the app and live in the plan
file. In production they come from the Helios KBD reference-data mapper; `reference.LISTS`
is where that feed lands, and the screen is the fallback until it exists. The closed lists
Helios owns outright — assurance functions, review teams, review types and categories — are
in `spec.py` and are not editable.

Removing a value does not strip it from the reviews that carry it. Those reviews keep it
and pre-staging then reports it as unrecognised: visible and fixable, rather than a silent
edit to someone else's plan.

## Relationship to `backend/`

The rules in `planning/` mirror `backend/app/domain/`, which is also pure standard library.
They are a port rather than an import on purpose: this app's value is that `python -m
helios` needs nothing installed and no repository layout around it, and reaching across
into `backend/` would give that up. The port is small enough to diff if the two ever have
to agree, and if `backend/` is retired nothing here moves.

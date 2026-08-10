# Helios bulk upload — CSV export

A lite app whose only job is to produce a **valid Helios bulk upload CSV**. It is a
narrowed rebuild of the pre-staging tab from the MVP prototype
(`2027_IAP_Planning_Module.html`), with the planning workflow around it left out.

Standard library only — no pip install, no Poetry, no Node, no database.

```
python3 -m helios                          # http://127.0.0.1:8000
python3 -m helios reviews.csv -o out.csv   # convert without opening a browser
python3 -m unittest discover -s helios/tests -t .
```

Or `make helios` / `make test-helios` from the repository root.

## What it does

Five responsibilities, one per module. Nothing else is in scope.

| Module | Responsibility |
| --- | --- |
| `spec.py` | The 27 Helios columns, their allowed values, the required set, the derived fields |
| `reference.py` | Reference data, and normalisation onto canonical spellings |
| `mapping.py` | Approved reviews → Helios columns |
| `validation.py` | Required fields and allowed values, with explicit per-row errors |
| `export.py` | The CSV itself |

`server.py` is a thin HTTP layer over those and holds no rules of its own, so the file the
browser downloads is byte-identical to the one the CLI writes.

Deliberately **not** here: scoring, weighting, capacity and FTE modelling, SME allocation,
staging, quarter scheduling, approval routing, plan versioning, audit trail, users and
roles. Those live in `backend/` and are not needed to produce the CSV.

## The pipeline

```
approved reviews ──▶ mapping ──▶ normalisation ──▶ validation ──▶ CSV
                    (columns)    (canonical)      (all or nothing)
```

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

| | |
| --- | --- |
| `GET /` | the single-page UI |
| `GET /api/spec` | columns, allowed values, reference lists, a blank row |
| `POST /api/import` | `{"csv": "..."}` or `{"reviews": [...]}` → mapped rows + errors |
| `POST /api/validate` | `{"rows": [...]}` → normalised rows + errors |
| `POST /api/export` | `{"rows": [...]}` → the CSV, or `422` with the errors that stopped it |

The UI keeps rows in `localStorage` and holds no validation logic of its own — every check
is the server's, so what you see on screen is what the export will enforce.

## Reference data

`reference.py` holds the business and location lists. In production these come from the
Helios KBD reference-data mapper; `LISTS` is where that feed lands. The closed lists that
Helios owns outright (assurance functions, review teams, review types and categories) are
in `spec.py`.

"""The planning workflow: everything upstream of the Helios CSV.

    constants    methodology facts — quarters, sizes, bands, routes
    types        the plan's data model, and its JSON shape
    errors       the refusals the methodology requires
    scoring      weighted priority, overrides, bands            (rules 2, 3, 5)
    staging      staging and descoping                          (rules 4, 6)
    capacity     FTE demand against per-quarter capacity        (rules 7, 8)
    scheduling   waterfall Q1 → Q4 auto-fill                    (rule 9)
    approval     routes, gates and sign-off                     (rule 10)
    seed         the synthetic candidate list
    store        the plan on disk, the audit trail, versions    (rule 11)
    actions      the mutations the UI performs, each audited

The rules here mirror `backend/app/domain/`, which is also pure standard library. They are
a port rather than an import on purpose: this app's whole value is that `python -m helios`
needs nothing installed and no repository layout around it, and importing across into
`backend/` would give that up. If the two ever have to agree, the port is small enough to
diff — and if `backend/` is retired, nothing here moves.
"""

from . import (
    approval,
    capacity,
    constants,
    errors,
    scheduling,
    scoring,
    seed,
    staging,
    store,
    types,
)

__all__ = [
    "approval",
    "capacity",
    "constants",
    "errors",
    "scheduling",
    "scoring",
    "seed",
    "staging",
    "store",
    "types",
]

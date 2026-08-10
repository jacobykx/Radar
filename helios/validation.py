"""Row validation: normalise, then reject anything Helios would reject, with a reason.

`prepare` is the only path a row takes on its way to the CSV. It is deliberately total —
it never raises on bad input, it returns the cleaned row plus every problem found, so the
caller can show all of them at once instead of one per attempt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import reference, spec


@dataclass(frozen=True)
class Error:
    """One problem with one cell. `row` is 1-based, matching what the user sees."""

    row: int
    field: str
    label: str
    code: str  # required | unknown_value | bad_date
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "row": self.row,
            "field": self.field,
            "label": self.label,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class Prepared:
    """A batch after normalisation. `ok` is what the CSV writer gates on."""

    rows: list[dict[str, str]] = field(default_factory=list)
    errors: list[Error] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def errors_for(self, row: int) -> list[Error]:
        return [e for e in self.errors if e.row == row]


def prepare_row(values: dict[str, object], row: int = 1) -> tuple[dict[str, str], list[Error]]:
    """Normalise one row and collect its errors.

    Every spec field is present in the returned row, so the writer never has to guess at a
    missing key and the column count is stable across rows.
    """
    clean: dict[str, str] = {}
    errors: list[Error] = []
    target_start = None

    for f in spec.FIELDS:
        if f.type == "derived":
            continue  # recomputed below; never taken from the caller

        raw = values.get(f.key, "")

        if f.type == "multi":
            joined, unknown = reference.normalise_many(raw, reference.choices_for(f.reference))
            clean[f.key] = joined
            for value in unknown:
                errors.append(_unknown(row, f, value, reference.choices_for(f.reference)))

        elif f.type == "date":
            parsed = spec.parse_date(raw)
            clean[f.key] = parsed.iso
            if not parsed.ok:
                errors.append(Error(
                    row, f.key, f.label, "bad_date",
                    f"{f.label}: {parsed.raw!r} is not a date. Use {spec.date_formats()}.",
                ))
            target_start = parsed.value

        elif choices := (f.allowed or reference.choices_for(f.reference)):
            # An off-list value is kept, not blanked: blanking it would hide what needs
            # fixing and would also make the field report as merely "required", which is
            # both wrong and unhelpful when the person did fill it in.
            value, ok = reference.normalise(raw, choices)
            clean[f.key] = value
            if not ok:
                errors.append(_unknown(row, f, value, choices))

        else:
            clean[f.key] = str(raw or "").strip()

    clean.update(spec.derive(target_start))

    errors.extend(
        Error(row, key, spec.BY_KEY[key].label, "required",
              f"{spec.BY_KEY[key].label} is required.")
        for key in spec.REQUIRED
        if not clean.get(key, "").strip()
    )

    errors.sort(key=lambda e: _order(e.field))
    return clean, errors


def prepare(rows: list[dict[str, object]]) -> Prepared:
    """Normalise and validate a batch, numbering rows from 1."""
    out = Prepared()
    for index, values in enumerate(rows, start=1):
        clean, errors = prepare_row(values, index)
        out.rows.append(clean)
        out.errors.extend(errors)
    return out


def _unknown(row: int, f: spec.Field, value: str, choices: tuple[str, ...]) -> Error:
    """An off-list value. The message carries the near miss, because that is usually the fix."""
    suggestion = _closest(value, choices)
    tail = f" Did you mean {suggestion!r}?" if suggestion else f" Allowed: {_sample(choices)}."
    return Error(
        row, f.key, f.label, "unknown_value",
        f"{f.label}: {value!r} is not a recognised value.{tail}",
    )


def _closest(value: str, choices: tuple[str, ...]) -> str | None:
    """A cheap prefix/substring match — enough to catch truncations and stray suffixes."""
    wanted = reference.key(value)
    if not wanted:
        return None
    for choice in choices:
        candidate = reference.key(choice)
        if candidate.startswith(wanted) or wanted.startswith(candidate):
            return choice
    return next((c for c in choices if wanted in reference.key(c)), None)


def _sample(choices: tuple[str, ...], limit: int = 4) -> str:
    shown = ", ".join(repr(c) for c in choices[:limit])
    return f"{shown}, …" if len(choices) > limit else shown


def _order(key: str) -> int:
    return next((i for i, f in enumerate(spec.FIELDS) if f.key == key), len(spec.FIELDS))

"""Generate the Helios bulk upload CSV.

Strict by design: a batch with any error produces no file. A partially valid upload is
worse than no upload — Helios takes the good rows, and the rejected ones are then missing
from the plan with nothing on screen to say so.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass, field

from . import spec, validation


@dataclass
class Export:
    """The outcome of an export attempt. `csv` is empty whenever `errors` is not."""

    csv: str = ""
    errors: list[validation.Error] = field(default_factory=list)
    rows: int = 0
    filename: str = "IAP_Helios_upload.csv"

    @property
    def ok(self) -> bool:
        return not self.errors


def table(header: list[str], rows: list[list[object]]) -> str:
    """Render any table as CSV, on the terms every export here uses.

    QUOTE_ALL and CRLF: Helios's loader is quote-tolerant but not delimiter-tolerant, and
    the free-text columns routinely contain commas and newlines. The governance exports
    use the same settings so every file the tool emits opens the same way.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(["" if cell is None else cell for cell in row] for row in rows)
    return buffer.getvalue()


def write(rows: list[dict[str, str]]) -> str:
    """Render prepared Helios rows. Assumes the rows have already been validated."""
    return table(spec.HEADER, [[row.get(f.key, "") for f in spec.FIELDS] for row in rows])


def build(rows: list[dict[str, object]]) -> Export:
    """Validate, then generate. The one entry point the server and the CLI both use."""
    if not rows:
        return Export(errors=[validation.Error(
            0, "", "", "empty", "There are no reviews to export.",
        )])

    prepared = validation.prepare(rows)
    if not prepared.ok:
        return Export(errors=prepared.errors)

    return Export(
        csv=write(prepared.rows),
        rows=len(prepared.rows),
        filename=filename(prepared.rows),
    )


def filename(rows: list[dict[str, str]]) -> str:
    """Name the file after the plan year the batch mostly falls in."""
    years = Counter(row.get("planYear", "") for row in rows if row.get("planYear"))
    year = years.most_common(1)[0][0] if years else ""
    return f"{year}_IAP_Helios_upload.csv" if year else "IAP_Helios_upload.csv"

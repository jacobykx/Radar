"""Run the app, or convert a CSV of approved reviews straight to a Helios upload file.

    python3 -m helios                          serve the UI on http://127.0.0.1:8000
    python3 -m helios --port 9000              serve on another port
    python3 -m helios reviews.csv              convert, writing the CSV to stdout
    python3 -m helios reviews.csv -o out.csv   convert, writing to a file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import export, mapping, server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="helios", description=__doc__.splitlines()[0])
    parser.add_argument("source", nargs="?", help="CSV of approved reviews to convert")
    parser.add_argument("-o", "--out", help="write the Helios CSV here instead of stdout")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    # Messages carry em dashes and ellipses. An older Windows console code page cannot
    # encode those, and a crash while reporting an error is the worst time to have one.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    if args.source is None:
        server.serve(args.host, args.port)
        return 0

    return convert(Path(args.source), Path(args.out) if args.out else None)


def convert(source: Path, out: Path | None) -> int:
    """Map, validate and write. Errors go to stderr and nothing is written."""
    if not source.is_file():
        print(f"{source}: no such file", file=sys.stderr)
        return 2

    rows, ignored = mapping.from_csv(read_text(source))
    if ignored:
        print(f"ignored {len(ignored)} unrecognised column(s): {', '.join(ignored)}",
              file=sys.stderr)

    result = export.build(rows)
    if not result.ok:
        print(f"{len(result.errors)} problem(s) — nothing written:", file=sys.stderr)
        for error in result.errors:
            print(f"  row {error.row}: {error.message}", file=sys.stderr)
        return 1

    if out:
        # newline="" keeps the CRLF the writer already put in; without it Windows would
        # translate again and every line would end \r\r\n.
        with out.open("w", encoding="utf-8", newline="") as handle:
            handle.write(result.csv)
        print(f"{result.rows} row(s) -> {out}", file=sys.stderr)
    else:
        # Bytes, not sys.stdout.write: a redirected stdout on Windows encodes with the
        # console code page, which would silently emit a cp1252 file whose em dashes
        # Helios cannot read. The CSV is UTF-8 wherever it is written.
        sys.stdout.buffer.write(result.csv.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


#: Tried in order. utf-8-sig first because it also covers plain UTF-8 and strips any BOM;
#: cp1252 second because it is what Excel's default "CSV (Comma delimited)" writes on
#: Windows, and decoding it as UTF-8 fails on the first em dash or smart quote.
_ENCODINGS = ("utf-8-sig", "cp1252")


def read_text(source: Path) -> str:
    """Read a CSV whatever the machine that saved it used."""
    raw = source.read_bytes()
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # cp1252 leaves only five bytes undefined, so getting here means the file is binary.
    print(f"{source}: not readable as text — is it really a CSV?", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())

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

    if args.source is None:
        server.serve(args.host, args.port)
        return 0

    return convert(Path(args.source), Path(args.out) if args.out else None)


def convert(source: Path, out: Path | None) -> int:
    """Map, validate and write. Errors go to stderr and nothing is written."""
    if not source.is_file():
        print(f"{source}: no such file", file=sys.stderr)
        return 2

    rows, ignored = mapping.from_csv(source.read_text(encoding="utf-8"))
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
        out.write_text(result.csv, encoding="utf-8", newline="")
        print(f"{result.rows} row(s) -> {out}", file=sys.stderr)
    else:
        sys.stdout.write(result.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

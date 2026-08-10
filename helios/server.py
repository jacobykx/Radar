"""A thin HTTP layer over the five responsibilities. Standard library only.

Deliberately not a framework: this app has four endpoints and no database, and keeping it
dependency-free means `python3 -m helios` is the whole install story.

    GET  /                 the single-page UI
    GET  /api/spec         the column spec and reference lists
    POST /api/import       CSV or JSON of approved reviews -> mapped Helios rows
    POST /api/validate     rows -> normalised rows + explicit errors
    POST /api/export       rows -> the CSV, or 422 with the errors that stopped it
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import export, mapping, reference, spec, validation

STATIC = Path(__file__).parent / "static"
MAX_BODY = 8 * 1024 * 1024  # a plan is a few hundred rows; anything larger is a mistake


class Handler(BaseHTTPRequestHandler):
    server_version = "helios-csv"

    # ------------------------------------------------------------------ routes

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's naming
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8")
        if route == "/api/spec":
            return self._json(200, _spec_payload())
        self._json(404, {"error": f"No route for GET {route}."})

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        try:
            body = self._body()
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})

        if route == "/api/import":
            return self._import(body)
        if route == "/api/validate":
            return self._validate(body)
        if route == "/api/export":
            return self._export(body)
        self._json(404, {"error": f"No route for POST {route}."})

    # ------------------------------------------------------------- handlers

    def _import(self, body: dict) -> None:
        """Map approved reviews — pasted CSV or a JSON list — onto Helios columns."""
        text = body.get("csv")
        if isinstance(text, str) and text.strip():
            rows, unknown = mapping.from_csv(text)
        else:
            reviews = body.get("reviews") or []
            if not isinstance(reviews, list):
                return self._json(400, {"error": "'reviews' must be a list of objects."})
            rows, unknown = mapping.to_helios_many(reviews), []

        prepared = validation.prepare(rows)
        self._json(200, {
            "rows": prepared.rows,
            "errors": [e.as_dict() for e in prepared.errors],
            "ignored_columns": unknown,
        })

    def _validate(self, body: dict) -> None:
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            return self._json(400, {"error": "'rows' must be a list of objects."})

        prepared = validation.prepare(rows)
        self._json(200, {
            "rows": prepared.rows,
            "errors": [e.as_dict() for e in prepared.errors],
            "ready": sum(1 for i in range(1, len(prepared.rows) + 1) if not prepared.errors_for(i)),
        })

    def _export(self, body: dict) -> None:
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            return self._json(400, {"error": "'rows' must be a list of objects."})

        result = export.build(rows)
        if not result.ok:
            # 422: the request was well-formed, the plan data was not.
            return self._json(422, {"errors": [e.as_dict() for e in result.errors]})

        # Excel mangles the em dashes in the business names without a BOM; Helios's own
        # loader is happier without one. Default to the machine consumer, opt in for Excel.
        encoding = "utf-8-sig" if "bom=1" in self.path else "utf-8"
        payload = result.csv.encode(encoding)
        self._send(200, payload, "text/csv; charset=utf-8", extra={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        })

    # -------------------------------------------------------------- plumbing

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Request body is too large.")
        if not length:
            return {}
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Body is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Body must be a JSON object.")
        return parsed

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _file(self, name: str, content_type: str) -> None:
        path = STATIC / name
        if not path.is_file():
            return self._json(404, {"error": f"{name} is missing."})
        self._send(200, path.read_bytes(), content_type)

    def _send(self, status: int, payload: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # the default logs every request to stderr; too noisy for a local tool


def _spec_payload() -> dict:
    return {
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "group": f.group,
                "hint": f.hint,
                "full_width": f.full_width,
                "required": f.required,
                "allowed": list(f.allowed) or list(reference.choices_for(f.reference)) or None,
            }
            for f in spec.FIELDS
        ],
        "required": list(spec.REQUIRED),
        "blank": mapping.blank_row(),
    }


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Helios CSV export — http://{host}:{port}  (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()

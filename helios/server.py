"""A thin HTTP layer over the rules. Standard library only.

Deliberately not a framework. Two shapes of route:

    GET  /                     the single-page UI
    GET  /api/plan             the whole plan, with everything the screens derive
    POST /api/op/<name>        one named mutation, then the whole plan again
    GET  /api/export/<what>    helios | plan | approvals | audit  → a CSV download

and the stateless CSV endpoints the CLI and any caller can use without a plan file:

    GET  /api/spec             the Helios column spec
    POST /api/import           approved reviews → mapped Helios rows
    POST /api/validate         rows → normalised rows + explicit errors
    POST /api/export           rows → the CSV, or 422 with the errors that stopped it

Every mutation goes through `ops`, so nothing can change the plan without an audit line.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import export, mapping, reference, spec, validation
from .planning import actions, exports, prestaging, views
from .planning.errors import NotFound, PlanningError
from .planning.store import DEFAULT_PATH, Store

__all__ = ["DEFAULT_PATH", "Handler", "serve"]

STATIC = Path(__file__).parent / "static"
MAX_BODY = 8 * 1024 * 1024  # a plan is a few hundred rows; anything larger is a mistake


# --------------------------------------------------------------------------- operations

#: name -> callable(plan, body, user). The UI never names anything else.
OPS = {
    "weights": lambda p, b, u: actions.set_weights(p, b.get("weights") or {}, user=u),
    "weights.reset": lambda p, b, u: actions.reset_weights(p, user=u),

    "stage": lambda p, b, u: actions.stage(p, b["ref"], user=u),
    "descope": lambda p, b, u: actions.descope(p, b["ref"], b.get("rationale", ""), user=u),
    "stage.critical_and_high": lambda p, b, u: actions.stage_critical_and_high(p, user=u),
    "stage.clear": lambda p, b, u: actions.clear_staging(p, user=u),

    "priority": lambda p, b, u: actions.override_priority(
        p, b["ref"], b.get("value", 0), b.get("rationale", ""), user=u),
    "priority.clear": lambda p, b, u: actions.clear_override(p, b["ref"], user=u),

    "effort": lambda p, b, u: actions.set_effort(p, b["ref"], b["size"], user=u),
    "fte": lambda p, b, u: actions.set_fte(p, b["ref"], b.get("fte"), user=u),
    "quarter": lambda p, b, u: actions.set_quarter(p, b["ref"], b.get("quarter"), user=u),
    "quarters.waterfall": lambda p, b, u: actions.waterfall(p, user=u),
    "quarters.clear": lambda p, b, u: actions.clear_quarters(p, user=u),
    "capacity": lambda p, b, u: actions.set_capacity(
        p, b["function"], b.get("fte_per_quarter", 0), user=u),

    "review.add": lambda p, b, u: actions.add_review(p, b, user=u).ref,
    "review.remove": lambda p, b, u: actions.remove_review(p, b["ref"], user=u),
    "review.comment": lambda p, b, u: actions.add_comment(p, b["ref"], b.get("text", ""), user=u),
    "review.steward": lambda p, b, u: actions.set_steward(
        p, b["ref"], b.get("name", ""), b.get("consulted", True), user=u),
    "review.locations": lambda p, b, u: actions.set_locations(
        p, b["ref"], b.get("locations") or [], user=u),

    "signoff": lambda p, b, u: actions.sign_off(
        p, b["ref"], b.get("decision", ""), b.get("note", ""), user=u),

    "prestaging": lambda p, b, u: actions.update_prestaging(
        p, b["ref"], b.get("changes") or {}, user=u),

    "version.save": lambda p, b, u: p.save_version(
        user=u, label=b.get("label", ""), note=b.get("note", "")).summary(),
    "version.restore": lambda p, b, u: p.restore_version(b["id"], user=u).summary(),

    "reference": lambda p, b, u: actions.set_reference(
        p, b.get("kind", ""), b.get("values") or [], user=u),
}

EXPORTS = {
    "plan": (exports.plan_csv, "IAP_shaped_plan.csv"),
    "approvals": (exports.approval_csv, "IAP_approval_view.csv"),
    "audit": (exports.audit_csv, "IAP_audit_trail.csv"),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "helios-iap"
    store: Store = Store()

    # ------------------------------------------------------------------ routes

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's naming
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8")
        if route == "/api/spec":
            return self._json(200, _spec_payload())
        if route == "/api/plan":
            return self._json(200, views.whole(self.store.load()))
        if route.startswith("/api/prestaging/"):
            return self._prestaging(unquote(route.rsplit("/", 1)[-1]))
        if route.startswith("/api/export/"):
            return self._export_named(route.rsplit("/", 1)[-1])
        self._json(404, {"error": f"No route for GET {route}."})

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        try:
            body = self._body()
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})

        if route.startswith("/api/op/"):
            return self._operation(route.rsplit("/", 1)[-1], body)
        if route == "/api/import":
            return self._import(body)
        if route == "/api/validate":
            return self._validate(body)
        if route == "/api/export":
            return self._export_rows(body)
        if route == "/api/reset":
            self.store.reset()
            return self._json(200, views.whole(self.store.load()))
        self._json(404, {"error": f"No route for POST {route}."})

    # ------------------------------------------------------------- the plan

    def _operation(self, name: str, body: dict) -> None:
        handler = OPS.get(name)
        if handler is None:
            return self._json(404, {"error": f"{name!r} is not an operation."})

        user = (body.get("user") or "").strip()
        try:
            with self.store.mutate() as plan:
                result = handler(plan, body, user)
                payload = views.whole(plan)
        except PlanningError as exc:
            # 422: the request was well-formed, the methodology refused it.
            return self._json(422, {"error": str(exc)})
        except KeyError as exc:
            return self._json(400, {"error": f"{exc.args[0]!r} is required for {name!r}."})
        except (ValueError, TypeError) as exc:
            return self._json(400, {"error": str(exc)})

        payload["result"] = result if _jsonable(result) else None
        self._json(200, payload)

    def _prestaging(self, ref: str) -> None:
        """One review's Helios record: normalised values and the exact per-field errors."""
        try:
            review = self.store.load().review(ref)
        except NotFound as exc:
            return self._json(404, {"error": str(exc)})
        self._json(200, prestaging.read(review))

    def _export_named(self, what: str) -> None:
        plan = self.store.load()
        if what == "helios":
            result = export.build(exports.helios_rows(plan))
            if not result.ok:
                return self._json(422, {"errors": [e.as_dict() for e in result.errors]})
            return self._csv(result.csv, f"{plan.year}_{result.filename.split('_', 1)[-1]}")

        entry = EXPORTS.get(what)
        if entry is None:
            return self._json(404, {"error": f"No export named {what!r}."})
        build, name = entry
        self._csv(build(plan), f"{plan.year}_{name}")

    # ------------------------------------------------- stateless CSV endpoints

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
        ready = sum(1 for i in range(1, len(prepared.rows) + 1) if not prepared.errors_for(i))
        self._json(200, {
            "rows": prepared.rows,
            "errors": [e.as_dict() for e in prepared.errors],
            "ready": ready,
        })

    def _export_rows(self, body: dict) -> None:
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            return self._json(400, {"error": "'rows' must be a list of objects."})

        result = export.build(rows)
        if not result.ok:
            return self._json(422, {"errors": [e.as_dict() for e in result.errors]})
        self._csv(result.csv, result.filename)

    # -------------------------------------------------------------- plumbing

    def _csv(self, text: str, filename: str) -> None:
        # Excel mangles the em dashes in the business names without a BOM; Helios's own
        # loader is happier without one. Default to the machine consumer, opt in for Excel.
        encoding = "utf-8-sig" if "bom=1" in self.path else "utf-8"
        self._send(200, text.encode(encoding), "text/csv; charset=utf-8", extra={
            "Content-Disposition": f'attachment; filename="{filename}"',
        })

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


def _jsonable(value: object) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


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


def serve(host: str = "127.0.0.1", port: int = 8000, data: Path | str = DEFAULT_PATH) -> None:
    Handler.store = Store(data)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"IAP planning module — http://{host}:{port}")
    print(f"plan file: {Handler.store.path.resolve()}  (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()

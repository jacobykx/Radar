"""The plan, and where it lives.

One JSON document holds everything: reviews, weights, capacities, reference data, the
audit trail and saved versions. The prototype kept this in `localStorage`, which means the
audit trail — the one artefact governance actually asks for — dies with the browser
profile. A file on disk survives, can be committed or attached to a pack, and lets the CLI
export from exactly what the UI is showing.

Writes are atomic: a temp file in the same directory, then `os.replace`, which is atomic on
Windows as well as POSIX. A crash mid-save leaves the previous plan intact rather than a
half-written one.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import seed
from .errors import NotFound, PlanFileError
from .types import FunctionCapacity, Review, Weights

#: Bumped only when the on-disk shape changes incompatibly.
SCHEMA = 1

DEFAULT_PATH = Path("iap-plan.json")


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class AuditEntry:
    """Append-only. There is deliberately no edit or delete path (rule 11)."""

    at: str
    user: str
    ref: str
    action: str
    detail: str

    def to_dict(self) -> dict:
        return {"at": self.at, "user": self.user, "ref": self.ref,
                "action": self.action, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict) -> AuditEntry:
        return cls(at=data.get("at", ""), user=data.get("user", ""), ref=data.get("ref", ""),
                   action=data.get("action", ""), detail=data.get("detail", ""))


@dataclass
class Version:
    """A named snapshot of the shaped plan, for comparing one cut against another."""

    id: str
    at: str
    user: str
    label: str
    note: str
    snapshot: dict

    def summary(self) -> dict:
        reviews = self.snapshot.get("reviews", [])
        in_plan = [r for r in reviews if r.get("staged") and not (
            r.get("descope_rationale") or "").strip()]
        return {
            "id": self.id,
            "at": self.at,
            "user": self.user,
            "label": self.label,
            "note": self.note,
            "reviews": len(reviews),
            "in_plan": len(in_plan),
            "mandated": len([r for r in in_plan if r.get("mandated")]),
        }

    def to_dict(self) -> dict:
        return {"id": self.id, "at": self.at, "user": self.user, "label": self.label,
                "note": self.note, "snapshot": self.snapshot}

    @classmethod
    def from_dict(cls, data: dict) -> Version:
        return cls(id=data.get("id", ""), at=data.get("at", ""), user=data.get("user", ""),
                   label=data.get("label", ""), note=data.get("note", ""),
                   snapshot=data.get("snapshot") or {})


@dataclass
class Plan:
    """Everything the module knows. Serialises whole, restores whole."""

    year: str = seed.PLAN_YEAR
    weights: Weights = field(default_factory=Weights)
    reviews: list[Review] = field(default_factory=list)
    capacities: list[FunctionCapacity] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)
    versions: list[Version] = field(default_factory=list)
    #: Editable reference lists. In production these come from the Helios KBD mapper;
    #: holding them in the plan is what makes the reference-data screen the fallback.
    reference: dict[str, list] = field(default_factory=dict)

    @classmethod
    def seeded(cls) -> Plan:
        return cls(reviews=seed.reviews(), capacities=seed.capacities(),
                   reference=seed.reference())

    # ---- access

    def review(self, ref: str) -> Review:
        for r in self.reviews:
            if r.ref == ref:
                return r
        raise NotFound(f"No review {ref!r} in the plan.")

    def capacity(self, function: str) -> FunctionCapacity:
        for c in self.capacities:
            if c.name == function:
                return c
        return FunctionCapacity(name=function, fte_per_quarter=0)

    def next_ref(self, prefix: str) -> str:
        """`EXT-1`, `EXT-2`, … — the first free number, so a delete does not reuse a ref."""
        taken = {r.ref for r in self.reviews}
        n = 1
        while f"{prefix}-{n}" in taken:
            n += 1
        return f"{prefix}-{n}"

    # ---- audit

    def log(self, user: str, action: str, detail: str = "", ref: str = "—") -> AuditEntry:
        entry = AuditEntry(at=now(), user=user or "Unattributed", ref=ref,
                           action=action, detail=detail)
        self.audit.insert(0, entry)  # newest first, as the prototype shows it
        return entry

    # ---- serialisation

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "year": self.year,
            "weights": self.weights.to_dict(),
            "reviews": [r.to_dict() for r in self.reviews],
            "capacities": [{"name": c.name, "fte_per_quarter": c.fte_per_quarter}
                           for c in self.capacities],
            "audit": [a.to_dict() for a in self.audit],
            "versions": [v.to_dict() for v in self.versions],
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Plan:
        return cls(
            year=data.get("year", seed.PLAN_YEAR),
            weights=Weights.from_dict(data.get("weights")),
            reviews=[Review.from_dict(r) for r in data.get("reviews") or []],
            capacities=[FunctionCapacity(name=c["name"], fte_per_quarter=int(c["fte_per_quarter"]))
                        for c in data.get("capacities") or []] or seed.capacities(),
            audit=[AuditEntry.from_dict(a) for a in data.get("audit") or []],
            versions=[Version.from_dict(v) for v in data.get("versions") or []],
            reference=data.get("reference") or seed.reference(),
        )

    # ---- versions

    def snapshot(self) -> dict:
        """What a version captures: the shaped plan, not the audit trail behind it."""
        return {
            "weights": self.weights.to_dict(),
            "reviews": [r.to_dict() for r in self.reviews],
        }

    def save_version(self, *, user: str, label: str, note: str = "") -> Version:
        version = Version(id=str(len(self.versions) + 1), at=now(), user=user or "Unattributed",
                          label=label.strip() or f"Version {len(self.versions) + 1}",
                          note=note.strip(), snapshot=self.snapshot())
        self.versions.append(version)
        self.log(user, "Version saved", f"{version.label} ({version.summary()['in_plan']} in plan)")
        return version

    def restore_version(self, version_id: str, *, user: str) -> Version:
        """Restore the shaped plan. The audit trail is not rewound — it records the restore."""
        for version in self.versions:
            if version.id == version_id:
                self.weights = Weights.from_dict(version.snapshot.get("weights"))
                self.reviews = [Review.from_dict(r) for r in version.snapshot.get("reviews", [])]
                self.log(user, "Version restored", version.label)
                return version
        raise NotFound(f"No version {version_id!r}.")


class Store:
    """Reads and writes one plan file. Serialises writes; safe for the threaded server."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> Plan:
        if not self.path.is_file():
            return Plan.seeded()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PlanFileError(f"{self.path} is not a readable plan file: {exc}") from exc
        return Plan.from_dict(data)

    def save(self, plan: Plan) -> None:
        """Atomic: write alongside, then replace. Never leaves a half-written plan."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Serialise before touching the disk, so a plan that cannot be encoded fails without
        # having already created a temp file next to a perfectly good one.
        payload = json.dumps(plan.to_dict(), indent=2, ensure_ascii=False)

        fd, tmp = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp",
        )
        try:
            # newline="\n" so the file reads the same on Windows as anywhere else.
            with open(fd, "w", encoding="utf-8", newline="\n") as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, self.path)  # atomic on Windows too
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @contextmanager
    def mutate(self):
        """Load, hand over the plan, save what the caller changed — under one lock."""
        with self._lock:
            plan = self.load()
            yield plan
            self.save(plan)

    def reset(self) -> Plan:
        with self._lock:
            plan = Plan.seeded()
            self.save(plan)
            return plan

"""Write the synthetic fixtures out as an instance document for the POC UI.

The POC front end runs the workflow in the browser against a JSON instance rather than
against this service (see `frontend/lib/engine`). Both read the same fixtures, so this
script -- not a second copy of the data -- is what keeps them in step:

    python -m scripts.export_instance

It needs no dependencies and no database; `app.seed.data` is plain Python.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.seed import data

SCHEMA = "iap.instance/1"
PLAN_YEAR = 2027
DEFAULT_OUT = (
    Path(__file__).resolve().parents[2] / "frontend" / "public" / "instances" / "2027-iap.json"
)


def _quarter(go_live: date | None) -> str | None:
    return f"Q{(go_live.month - 1) // 3 + 1}" if go_live else None


def _review(spec: dict) -> dict:
    mandated = spec.get("mandated", False)
    go_live = spec.get("go_live")
    risk, urgency, coverage_gap, change = spec["scores"]
    rris = spec.get("rris_ids")

    return {
        "ref": spec["ref"],
        "title": spec["title"],
        # Rule 4: mandated implies Regulatory Assurance; seeded candidates come from the radar.
        "origin": "Regulatory Assurance" if mandated else "Risk Radar inputs",
        "mandated": mandated,
        "taxonomy_code": spec["taxonomy"],
        "assurance_function": spec["function"],
        "sub_team": spec.get("sub_team"),
        "business": spec.get("business"),
        "locations": list(spec.get("locations", [])),
        "effort_size": spec["size"].value,
        "fte_override": None,
        "regulator": spec.get("regulator"),
        "regulation": spec.get("regulation"),
        "rris_ids": [r.strip() for r in rris.split(";")] if rris else [],
        "rca_linked": spec["ref"] in data.RCA_LINKED,
        "go_live": go_live.isoformat() if go_live else None,
        "is_custom": False,
        "scores": {
            "risk": risk,
            "urgency": urgency,
            "coverage_gap": coverage_gap,
            "change": change,
            "source": "scoring-engine (synthetic)",
        },
        # Rule 5: mandated reviews are pinned into the plan, in their go-live quarter.
        "item": {
            "staged": mandated,
            "planned_quarter": _quarter(go_live) if mandated else None,
            "priority_override": None,
            "priority_override_rationale": None,
            "descope_rationale": None,
            "row_version": 1,
        },
        "approval": None,
        "steward": None,
        "notes": [],
    }


def build() -> dict:
    return {
        "schema": SCHEMA,
        "id": "2027-iap",
        "plan": {"year": PLAN_YEAR, "name": f"{PLAN_YEAR} Indicative Annual Plan"},
        # Stands in for the authentication gateway, which is not in front of a static file.
        "identity": {
            "username": "poc.planner",
            "ad_groups": ["IAP_PLANNER", "IAP_APPROVER", "IAP_ADMIN"],
            "roles": ["Planner", "Approver", "Admin"],
        },
        "reference": {
            "taxonomy": [{"code": code, "label": label} for code, label in data.TAXONOMY],
            "business": [{"code": name, "label": name} for name in data.BUSINESSES],
            "location": [{"code": name, "label": name} for name in data.LOCATIONS],
        },
        "assurance_functions": [
            {"name": name, "fte_per_quarter": fte, "is_active": fte > 0}
            for name, fte in data.ASSURANCE_FUNCTIONS.items()
        ],
        "sub_teams": {k: list(v) for k, v in data.SUB_TEAMS.items()},
        "weights": {"risk": 1, "urgency": 1, "coverage_gap": 1, "change": 1},
        "reviews": [_review(spec) for spec in data.REVIEWS],
        "audit": [],
        "versions": [],
        "revision": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

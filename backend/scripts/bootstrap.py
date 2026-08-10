"""Create the schema and load the synthetic fixtures.

Local development convenience. The schema itself comes from Alembic -- the same
migrations a deployed environment runs -- so a developer's database cannot drift away
from what SIT, UAT and PROD will get. Only the seed data is development-only.

    python -m scripts.bootstrap [--reset] [--no-seed]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.core.db import SessionLocal
from app.seed.loader import seed

#: backend/alembic.ini, resolved relative to this file so the script works from any cwd.
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "app" / "migrations"))
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="downgrade to base first, dropping every table"
    )
    parser.add_argument("--no-seed", action="store_true", help="migrate only, load no fixtures")
    args = parser.parse_args()

    config = _alembic_config()

    if args.reset:
        command.downgrade(config, "base")
        print("downgraded to base")

    command.upgrade(config, "head")
    print(f"schema at head ({settings.database_url.split('://', 1)[0]})")

    if args.no_seed:
        return

    with SessionLocal() as session:
        plan = seed(session)
        from app.models import Review

        count = session.query(Review).filter(Review.plan_id == plan.id).count()
        print(f"seeded plan {plan.year}: {count} reviews")


if __name__ == "__main__":
    main()

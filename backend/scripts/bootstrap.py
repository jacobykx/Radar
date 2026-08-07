"""Create the schema and load the synthetic fixtures.

Local development convenience. Deployed environments get their schema from Alembic
(`alembic upgrade head`) and start with no seed data.

    python -m scripts.bootstrap [--reset]
"""

from __future__ import annotations

import argparse

from app.core.db import SessionLocal, engine
from app.models import Base
from app.seed.loader import seed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop every table first")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
        print("dropped all tables")

    Base.metadata.create_all(engine)
    print(f"schema ready ({len(Base.metadata.tables)} tables)")

    with SessionLocal() as session:
        plan = seed(session)
        from app.models import Review

        count = session.query(Review).filter(Review.plan_id == plan.id).count()
        print(f"seeded plan {plan.year}: {count} reviews")


if __name__ == "__main__":
    main()

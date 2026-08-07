"""Alembic environment.

The URL comes from `IAP_DATABASE_URL` via application settings, never from alembic.ini,
so `alembic upgrade head` in any environment targets exactly the database the API will
use and no connection string is committed.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings

# Importing the models package registers every table on Base.metadata. Without this
# autogenerate would compare against an empty schema and propose dropping everything.
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep Alembic's attention on this application's own tables.

    Alembic's own bookkeeping table is not part of the schema under version control.
    """
    return not (type_ == "table" and name == "alembic_version")


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_object=include_object,
        # Detect column type changes as well as added/dropped columns.
        compare_type=True,
        # SQLite reflects a server default as the literal text "CURRENT_TIMESTAMP", which
        # never compares equal to func.now(), so every timestamp column looks changed on
        # the local fallback. Postgres reflects these faithfully, so the comparison stays
        # on for the dialect that is actually deployed.
        compare_server_default=not settings.is_sqlite,
        # SQLite cannot ALTER a column in place; batch mode rewrites the table instead.
        # Harmless on Postgres, and it keeps the local fallback migratable.
        render_as_batch=settings.is_sqlite,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DBAPI connection -- `alembic upgrade head --sql`.

    Useful where a DBA applies the change set by hand rather than the application
    connecting with DDL rights.
    """
    _configure(
        url=settings.database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _configure(connection=connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

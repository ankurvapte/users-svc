"""Alembic environment: applies migrations/versions to DATABASE_URL.

Run by the one-shot `users-migrate` container (`alembic upgrade head`)
before users-svc starts. Migrations are plain SQL through op.execute; the
app itself never uses SQLAlchemy, only Alembic does.
"""
from __future__ import annotations

import logging

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import load_settings
from app.logging_setup import configure_logging

config = context.config
settings = load_settings()

# Same JSON logs as the service, unless a caller (pytest) already set up logging.
if not logging.getLogger().handlers:
    configure_logging(settings.service_name, settings.log_level)


def _database_url() -> str:
    # Tests pass the URL in directly; containers use DATABASE_URL like the app.
    url = config.attributes.get("database_url") or settings.database_url
    if not url:
        raise SystemExit("DATABASE_URL is not set; nothing to migrate")
    # SQLAlchemy needs the driver in the URL; the app's URL is plain postgresql://.
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations() -> None:
    # lock_timeout: fail fast instead of queueing behind a long-held lock.
    engine = create_engine(
        _database_url(),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 5, "options": "-c lock_timeout=5000"},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline mode is not supported; run against a database")
run_migrations()

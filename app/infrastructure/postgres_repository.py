"""Infrastructure layer: a concrete UserRepository backed by PostgreSQL.

Used when DATABASE_URL is set. Nothing is kept in memory, so any number of
replicas can share one database. Like the JSON adapter, it never crashes
startup: if the database is unreachable it reports not-ready, and calls
fail with StorageUnavailable (503) until the database is back.

Tables come from Alembic migrations (`migrations/`), applied before the
service starts. This adapter never creates or changes them.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.application.ports import StorageUnavailable
from app.application.use_cases import EmailAlreadyExists
from app.domain.models import User, UserStatus
from app.infrastructure.json_repository import JsonUserRepository

logger = logging.getLogger(__name__)

_COLUMNS = "id, email, display_name, status, created_at, updated_at"


class PostgresUserRepository:
    def __init__(self, database_url: str, seed_file: str | None = None) -> None:
        self._seed_file = seed_file
        self._seed_checked = False
        # Design for failure: short connect/pool timeouts and a statement
        # timeout, so a slow or dead database turns into a fast 503.
        self._pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=5,
            timeout=2,
            open=False,
            kwargs={"row_factory": dict_row, "connect_timeout": 2, "options": "-c statement_timeout=5000"},
        )
        # wait=False: don't block startup on the database; connections are
        # retried in the background and /health/ready reflects the result.
        self._pool.open(wait=False)

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        # The pool commits on success and rolls back if the block raises.
        try:
            with self._pool.connection() as conn:
                if not self._seed_checked:
                    self._seed_if_empty(conn)
                yield conn
        except (psycopg.Error, PoolTimeout) as exc:
            logger.error("Database error", extra={"error": str(exc)})
            raise StorageUnavailable("User storage is unavailable") from exc

    def _seed_if_empty(self, conn: psycopg.Connection) -> None:
        # If migrations haven't run yet, the table is missing: this raises,
        # the service reports not-ready, and the next call tries again.
        empty = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM users) AS empty").fetchone()["empty"]
        if empty and self._seed_file:
            # Reuse the JSON adapter to parse and validate the seed file.
            seed = JsonUserRepository(self._seed_file).list_all()
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO users ({_COLUMNS}) VALUES "
                    "(%(id)s, %(email)s, %(display_name)s, %(status)s, %(created_at)s, %(updated_at)s) "
                    "ON CONFLICT DO NOTHING",
                    [self._to_record(u) for u in seed],
                )
            logger.info("Seeded users", extra={"count": len(seed), "path": self._seed_file})
        conn.commit()
        self._seed_checked = True

    @staticmethod
    def _to_domain(row: dict) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=UserStatus(row["status"]),
        )

    @staticmethod
    def _to_record(user: User) -> dict:
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status.value,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    def list_all(self) -> list[User]:
        with self._connection() as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM users").fetchall()
        return [self._to_domain(r) for r in rows]

    def get_by_id(self, user_id: str) -> User | None:
        with self._connection() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()
        return self._to_domain(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        with self._connection() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM users WHERE email = %s", (email,)).fetchone()
        return self._to_domain(row) if row else None

    def add(self, user: User) -> None:
        with self._connection() as conn:
            try:
                conn.execute(
                    f"INSERT INTO users ({_COLUMNS}) VALUES "
                    "(%(id)s, %(email)s, %(display_name)s, %(status)s, %(created_at)s, %(updated_at)s)",
                    self._to_record(user),
                )
            except UniqueViolation as exc:
                # The use case checks first; the UNIQUE constraint catches the
                # race where two requests register the same email at once.
                raise EmailAlreadyExists(user.email) from exc

    def update(self, user: User) -> None:
        with self._connection() as conn:
            try:
                conn.execute(
                    "UPDATE users SET email = %(email)s, display_name = %(display_name)s, "
                    "status = %(status)s, updated_at = %(updated_at)s WHERE id = %(id)s",
                    self._to_record(user),
                )
            except UniqueViolation as exc:
                raise EmailAlreadyExists(user.email) from exc

    def is_ready(self) -> bool:
        try:
            with self._connection() as conn:
                conn.execute("SELECT 1")
        except StorageUnavailable:
            return False
        return True

    def close(self) -> None:
        self._pool.close()

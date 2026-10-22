"""Contract tests for PostgresUserRepository and the Alembic migrations.

Needs a throwaway Postgres; every test drops the tables and runs the
migrations from scratch, so they also prove the migrations work:

    docker run --rm -d --name users-test-db -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17-alpine
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres pytest tests/test_postgres_repository.py
    docker stop users-test-db

Without TEST_DATABASE_URL only the "database down" test runs.
"""
import os
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.application.ports import StorageUnavailable  # noqa: E402
from app.application.use_cases import EmailAlreadyExists, UserService  # noqa: E402
from app.domain.models import User, UserStatus  # noqa: E402
from app.infrastructure.postgres_repository import PostgresUserRepository  # noqa: E402

DB_URL = os.getenv("TEST_DATABASE_URL")
SEED = ROOT / "data" / "users.json"
PRIYA = "u1b2c3d4-0001-4e5f-8a90-000000000001"


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = DB_URL
    return cfg


def reset_database() -> None:
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS users, alembic_version")


def table_exists(name: str) -> bool:
    with psycopg.connect(DB_URL) as conn:
        return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (name,)).fetchone()[0]


class DatabaseDownTests(unittest.TestCase):
    def test_unreachable_database_is_not_ready_and_raises_storage_unavailable(self):
        repo = PostgresUserRepository("postgresql://nobody:nothing@127.0.0.1:1/none")
        try:
            self.assertFalse(repo.is_ready())
            with self.assertRaises(StorageUnavailable):
                repo.get_by_id(PRIYA)
        finally:
            repo.close()


@unittest.skipUnless(DB_URL, "set TEST_DATABASE_URL to run Postgres tests")
class PostgresUserRepositoryTests(unittest.TestCase):
    def setUp(self):
        reset_database()
        command.upgrade(alembic_config(), "head")
        self.repo = PostgresUserRepository(DB_URL, seed_file=str(SEED))

    def tearDown(self):
        self.repo.close()

    def test_not_ready_until_migrated(self):
        reset_database()
        repo = PostgresUserRepository(DB_URL, seed_file=str(SEED))
        try:
            self.assertFalse(repo.is_ready())
            command.upgrade(alembic_config(), "head")
            self.assertTrue(repo.is_ready())
            self.assertEqual(len(repo.list_all()), 5)
        finally:
            repo.close()

    def test_migrations_downgrade_and_upgrade_again(self):
        command.downgrade(alembic_config(), "base")
        self.assertFalse(table_exists("users"))
        command.upgrade(alembic_config(), "head")
        self.assertTrue(table_exists("users"))

    def test_baseline_adopts_a_table_created_by_the_old_schema_sql(self):
        self.assertEqual(len(self.repo.list_all()), 5)
        with psycopg.connect(DB_URL, autocommit=True) as conn:
            conn.execute("DROP TABLE alembic_version")  # as if only schema.sql had run
        command.upgrade(alembic_config(), "head")
        self.assertEqual(len(self.repo.list_all()), 5)  # data kept

    def test_seeds_empty_table(self):
        self.assertTrue(self.repo.is_ready())
        users = self.repo.list_all()
        self.assertEqual(len(users), 5)
        self.assertEqual(sum(u.status == UserStatus.DISABLED for u in users), 1)

    def test_seed_runs_only_once(self):
        self.repo.list_all()
        second = PostgresUserRepository(DB_URL, seed_file=str(SEED))
        try:
            self.assertEqual(len(second.list_all()), 5)
        finally:
            second.close()

    def test_lookups_round_trip_the_entity(self):
        user = self.repo.get_by_id(PRIYA)
        self.assertEqual(user.email, "priya.sharma@example.com")
        self.assertEqual(self.repo.get_by_email("priya.sharma@example.com"), user)
        self.assertIsNone(self.repo.get_by_id("nope"))

    def test_add_and_update(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        user = User(id="new-1", email="new@example.com", display_name="New", created_at=now, updated_at=now)
        self.repo.add(user)
        self.assertEqual(self.repo.get_by_id("new-1"), user)

        disabled = replace(user, status=UserStatus.DISABLED)
        self.repo.update(disabled)
        self.assertEqual(self.repo.get_by_id("new-1").status, UserStatus.DISABLED)

    def test_unique_email_is_enforced_by_the_database(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        dup = User(id="dup-1", email="priya.sharma@example.com", display_name="Dup", created_at=now, updated_at=now)
        with self.assertRaises(EmailAlreadyExists):
            self.repo.add(dup)

    def test_works_behind_the_use_cases(self):
        service = UserService(self.repo)
        created = service.create_user("Someone@Example.com", "Someone")
        self.assertEqual(service.get_user(created.id).email, "someone@example.com")
        self.assertEqual(service.list_users(page_size=50).total, 6)


if __name__ == "__main__":
    unittest.main()

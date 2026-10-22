"""Unit tests for domain + application layers.

No FastAPI, no web server, no container needed. Runs with either:
    python -m unittest discover -s tests -p "test_use_cases.py"
    pytest tests/test_use_cases.py
"""
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.application.use_cases import (  # noqa: E402
    EmailAlreadyExists, UserFilter, UserNotFound, UserService,
)
from app.domain.models import InvalidUser, User, UserStatus  # noqa: E402
from app.infrastructure.json_repository import JsonUserRepository  # noqa: E402

SEED = ROOT / "data" / "users.json"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
PRIYA = "u1b2c3d4-0001-4e5f-8a90-000000000001"
RAHUL = "u1b2c3d4-0002-4e5f-8a90-000000000002"


class UserServiceTests(unittest.TestCase):
    def setUp(self):
        # Work on a copy so tests that write never touch the seed file.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        self.data_file = Path(tmp) / "users.json"
        shutil.copy(SEED, self.data_file)
        self.repo = JsonUserRepository(self.data_file)
        self.service = UserService(self.repo, clock=lambda: NOW, id_factory=lambda: "new-id")

    def test_loads_all_five_users(self):
        self.assertTrue(self.repo.is_ready())
        self.assertEqual(self.service.list_users(page_size=50).total, 5)

    def test_newest_first(self):
        dates = [u.created_at for u in self.service.list_users(page_size=50).items]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_filter_by_status(self):
        page = self.service.list_users(UserFilter(status=UserStatus.DISABLED))
        self.assertEqual([u.email for u in page.items], ["ananya.iyer@example.com"])

    def test_text_search(self):
        self.assertEqual(self.service.list_users(UserFilter(query="VERMA")).total, 1)

    def test_pagination(self):
        p2 = self.service.list_users(page=2, page_size=2)
        self.assertEqual((len(p2.items), p2.total, p2.total_pages), (2, 5, 3))

    def test_create_user(self):
        user = self.service.create_user("  New.Reader@Example.com ", " New Reader ")
        self.assertEqual(
            (user.id, user.email, user.display_name, user.status, user.created_at, user.updated_at),
            ("new-id", "new.reader@example.com", "New Reader", UserStatus.ACTIVE, NOW, NOW),
        )
        self.assertEqual(self.service.get_user("new-id"), user)

    def test_duplicate_email_is_case_insensitive(self):
        with self.assertRaises(EmailAlreadyExists):
            self.service.create_user("PRIYA.SHARMA@example.com", "Another Priya")

    def test_invalid_email_rejected(self):
        with self.assertRaises(InvalidUser):
            self.service.create_user("not-an-email", "Someone")

    def test_partial_update(self):
        user = self.service.update_user(PRIYA, display_name="Priya S.")
        self.assertEqual((user.display_name, user.email, user.updated_at), ("Priya S.", "priya.sharma@example.com", NOW))

    def test_disable_user(self):
        self.assertEqual(self.service.update_user(PRIYA, status=UserStatus.DISABLED).status, UserStatus.DISABLED)

    def test_email_change_conflict(self):
        with self.assertRaises(EmailAlreadyExists):
            self.service.update_user(PRIYA, email="rahul.verma@example.com")

    def test_keeping_own_email_is_not_a_conflict(self):
        self.assertEqual(self.service.update_user(RAHUL, email="Rahul.Verma@example.com").id, RAHUL)

    def test_missing_user_raises(self):
        with self.assertRaises(UserNotFound):
            self.service.get_user("does-not-exist")
        with self.assertRaises(UserNotFound):
            self.service.update_user("does-not-exist", display_name="X")

    def test_writes_persist_to_file(self):
        self.service.create_user("persist@example.com", "Persisted")
        self.service.update_user(PRIYA, status=UserStatus.DISABLED)
        reloaded = UserService(JsonUserRepository(self.data_file))
        self.assertEqual(reloaded.get_user("new-id").email, "persist@example.com")
        self.assertEqual(reloaded.get_user(PRIYA).status, UserStatus.DISABLED)

    def test_missing_data_file_reports_not_ready(self):
        self.assertFalse(JsonUserRepository(ROOT / "nope.json").is_ready())


class DomainRuleTests(unittest.TestCase):
    def _make(self, **overrides):
        fields = dict(id="x", email="a@b.co", display_name="A", created_at=NOW, updated_at=NOW)
        fields.update(overrides)
        return User(**fields)

    def test_bad_email_rejected(self):
        for email in ("no-at-sign", "a@b", "a b@c.d", "Upper@Case.com"):
            with self.subTest(email=email), self.assertRaises(InvalidUser):
                self._make(email=email)

    def test_blank_display_name_rejected(self):
        with self.assertRaises(InvalidUser):
            self._make(display_name="   ")

    def test_long_display_name_rejected(self):
        with self.assertRaises(InvalidUser):
            self._make(display_name="x" * 101)

    def test_updated_before_created_rejected(self):
        with self.assertRaises(InvalidUser):
            self._make(updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()

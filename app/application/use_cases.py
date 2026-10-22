"""Application layer: what the service can do (its use cases).

Orchestrates domain objects through the repository port. Knows nothing
about HTTP status codes, request objects or where data is stored.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from app.application.ports import UserRepository
from app.domain.models import User, UserStatus, normalize_email


class UserNotFound(Exception):
    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' not found")
        self.user_id = user_id


class EmailAlreadyExists(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(f"Email '{email}' is already registered")
        self.email = email


@dataclass(frozen=True)
class UserFilter:
    status: UserStatus | None = None
    query: str | None = None


@dataclass(frozen=True)
class Page:
    items: list[User]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        clock: Callable[[], datetime] = _utcnow,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._repo = repository
        self._clock = clock
        self._new_id = id_factory

    def list_users(self, filters: UserFilter = UserFilter(), page: int = 1, page_size: int = 10) -> Page:
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive")

        users = self._repo.list_all()
        if filters.status:
            users = [u for u in users if u.status == filters.status]
        if filters.query:
            users = [u for u in users if u.matches_text(filters.query)]

        users.sort(key=lambda u: u.created_at, reverse=True)
        start = (page - 1) * page_size
        return Page(items=users[start : start + page_size], total=len(users), page=page, page_size=page_size)

    def get_user(self, user_id: str) -> User:
        user = self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFound(user_id)
        return user

    def create_user(self, email: str, display_name: str) -> User:
        email = normalize_email(email)
        if self._repo.get_by_email(email) is not None:
            raise EmailAlreadyExists(email)
        now = self._clock()
        user = User(
            id=self._new_id(), email=email, display_name=display_name.strip(),
            created_at=now, updated_at=now,
        )
        self._repo.add(user)
        return user

    def update_user(
        self,
        user_id: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
        status: UserStatus | None = None,
    ) -> User:
        user = self.get_user(user_id)
        changes: dict = {}
        if email is not None:
            email = normalize_email(email)
            existing = self._repo.get_by_email(email)
            if existing is not None and existing.id != user.id:
                raise EmailAlreadyExists(email)
            changes["email"] = email
        if display_name is not None:
            changes["display_name"] = display_name.strip()
        if status is not None:
            changes["status"] = status
        if not changes:
            return user

        updated = replace(user, **changes, updated_at=self._clock())
        self._repo.update(updated)
        return updated

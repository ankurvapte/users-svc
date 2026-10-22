"""Ports: interfaces the application layer needs from the outside world.

Use cases depend on this abstraction, never on a concrete database.
Swapping the JSON file for Postgres later means writing a new class that
satisfies this Protocol. Nothing in the use cases or API changes.
"""
from __future__ import annotations

from typing import Protocol

from app.domain.models import User


class StorageUnavailable(Exception):
    """Raised by adapters when a write cannot be persisted."""


class UserRepository(Protocol):
    def list_all(self) -> list[User]: ...

    def get_by_id(self, user_id: str) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def add(self, user: User) -> None: ...

    def update(self, user: User) -> None: ...

    def is_ready(self) -> bool: ...

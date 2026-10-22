"""Domain layer: the core business entities.

Pure Python only. No FastAPI, no database, no JSON parsing here.
Everything else in the service depends on this module; it depends on nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

MAX_DISPLAY_NAME = 100
# Deliberately simple: one "@", no spaces, a dot in the domain part.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidUser(ValueError):
    """A business rule on User was broken."""


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


def normalize_email(email: str) -> str:
    # Emails are compared case-insensitively, so store one canonical form.
    return email.strip().lower()


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    created_at: datetime
    updated_at: datetime
    status: UserStatus = UserStatus.ACTIVE

    def __post_init__(self) -> None:
        # Business rules live with the entity, not in the HTTP layer.
        if self.email != normalize_email(self.email) or not _EMAIL_RE.match(self.email):
            raise InvalidUser(f"Invalid email '{self.email}'")
        if not self.display_name.strip():
            raise InvalidUser("display_name cannot be empty")
        if len(self.display_name) > MAX_DISPLAY_NAME:
            raise InvalidUser(f"display_name cannot exceed {MAX_DISPLAY_NAME} characters")
        if self.updated_at < self.created_at:
            raise InvalidUser("updated_at cannot be earlier than created_at")

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def matches_text(self, query: str) -> bool:
        q = query.lower()
        return q in self.email or q in self.display_name.lower()

"""API contract: request and response shapes exposed over HTTP (pillar 6).

Kept separate from domain models so the public contract can evolve
(v1, v2) without changing business entities, and vice versa.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models import MAX_DISPLAY_NAME, User, UserStatus


class UserCreateIn(BaseModel):
    # forbid: unknown fields (e.g. "password") are rejected with a 422
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    display_name: str = Field(min_length=1, max_length=MAX_DISPLAY_NAME)


class UserUpdateIn(BaseModel):
    """Partial update: only the fields sent are changed."""
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(None, max_length=254)
    display_name: str | None = Field(None, min_length=1, max_length=MAX_DISPLAY_NAME)
    status: UserStatus | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdateIn":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, u: User) -> "UserOut":
        return cls(
            id=u.id, email=u.email, display_name=u.display_name, status=u.status.value,
            created_at=u.created_at, updated_at=u.updated_at,
        )


class PaginationOut(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class UserListOut(BaseModel):
    data: list[UserOut]
    pagination: PaginationOut


class ErrorOut(BaseModel):
    """One consistent error format for every endpoint."""
    error: str
    message: str
    request_id: str | None = None

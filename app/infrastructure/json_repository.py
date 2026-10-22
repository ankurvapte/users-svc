"""Infrastructure layer: a concrete UserRepository backed by a JSON file.

This is the only place that knows the data lives in a file. In Docker the
file sits on a named volume, so writes survive container restarts. It only
works for a single replica; PostgresUserRepository will lift that limit
without touching other layers.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from app.application.ports import StorageUnavailable
from app.domain.models import User, UserStatus

logger = logging.getLogger(__name__)


class JsonUserRepository:
    def __init__(self, data_file: str | Path) -> None:
        self._path = Path(data_file)
        self._users: dict[str, User] = {}
        # Sync routes run in FastAPI's threadpool, so writes must be serialized.
        self._lock = threading.Lock()
        self._loaded = False
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            users = [self._to_domain(item) for item in raw]
        except (OSError, ValueError, KeyError) as exc:
            # Don't crash on startup: report not-ready so the orchestrator
            # keeps traffic away instead of restart-looping the container.
            logger.error("Failed to load users", extra={"path": str(self._path), "error": str(exc)})
            return
        self._users = {u.id: u for u in users}
        self._loaded = True
        logger.info("Loaded users", extra={"count": len(users), "path": str(self._path)})

    @staticmethod
    def _to_domain(item: dict) -> User:
        return User(
            id=item["id"],
            email=item["email"],
            display_name=item["display_name"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
            status=UserStatus(item.get("status", "active")),
        )

    @staticmethod
    def _to_record(user: User) -> dict:
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
            "status": user.status.value,
        }

    def _save(self, user: User) -> None:
        with self._lock:
            users = {**self._users, user.id: user}
            tmp = self._path.with_name(self._path.name + ".tmp")
            try:
                tmp.write_text(
                    json.dumps([self._to_record(u) for u in users.values()], indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(tmp, self._path)  # atomic: readers never see a half-written file
            except OSError as exc:
                logger.error("Failed to save users", extra={"path": str(self._path), "error": str(exc)})
                raise StorageUnavailable("User storage is unavailable") from exc
            # Only update memory once the write succeeded.
            self._users = users

    def list_all(self) -> list[User]:
        return list(self._users.values())

    def get_by_id(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    def add(self, user: User) -> None:
        self._save(user)

    def update(self, user: User) -> None:
        self._save(user)

    def is_ready(self) -> bool:
        return self._loaded

"""Configuration from environment variables only (pillar 4).

The same image runs in dev, test and prod; only these values change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str
    data_file: str
    database_url: str | None
    seed_file: str | None
    log_level: str
    default_page_size: int
    max_page_size: int


def load_settings() -> Settings:
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "users-svc"),
        data_file=os.getenv("DATA_FILE", "data/users.json"),
        # Set → PostgresUserRepository; unset → JsonUserRepository on DATA_FILE.
        database_url=os.getenv("DATABASE_URL") or None,
        # Optional: loaded into an empty users table on first connect.
        seed_file=os.getenv("SEED_FILE") or None,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        default_page_size=int(os.getenv("DEFAULT_PAGE_SIZE", "10")),
        max_page_size=int(os.getenv("MAX_PAGE_SIZE", "50")),
    )

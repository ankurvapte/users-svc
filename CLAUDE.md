# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Shared architecture rules and the container checklist live in `../CLAUDE.md` (from the [news-app-platform](https://github.com/ankurvapte/news-app-platform) repo).

users-svc: user accounts and profiles for the news app. No login, passwords or tokens (future auth service).
`README.md` is the public contract. Keep it in sync when the data model, endpoints or env vars change.

## Commands
- Unit tests (no deps): `python3 -m unittest discover -s tests -p "test_use_cases.py"`
- All tests: `pip install -r requirements-dev.txt && pytest` (Postgres tests skip unless `TEST_DATABASE_URL` is set; see README)
- Single test: `pytest tests/test_api.py::test_patch_user` or `python3 -m unittest tests.test_use_cases.UserServiceTests.test_create_user`
- Run locally: `uvicorn app.main:app --reload --port 8081` → http://localhost:8081/docs (no `DATABASE_URL`, so it writes to `DATA_FILE`)
- Run in Docker: `docker compose up --build` (users-svc on host port 8081 + `users-db` Postgres + one-shot `users-migrate`); reset data with `docker compose down -v`
- New migration: `alembic revision -m "<what>" --rev-id <next 4-digit number>` (no DB needed), then write plain SQL with `op.execute`
- No linter/formatter or pytest config is set up.

## Service-specific notes
- **Writes:** `UserService` takes an injectable `clock` and `id_factory` (tests pass fixed ones). Entities are frozen; updates use `dataclasses.replace` and always bump `updated_at`.
- **Email:** `normalize_email` (strip + lower) runs in the service before uniqueness checks. `User.__post_init__` rejects non-normalized or malformed emails with `InvalidUser` (→ 422). A duplicate raises `EmailAlreadyExists` (→ 409). An email change that matches the user's own email is not a conflict.
- **No visibility filter:** unlike articles, disabled users are still returned; clients filter with `?status=`.
- **JSON adapter:** `JsonUserRepository._save` holds a `threading.Lock`, writes `users.json.tmp` then `os.replace` (atomic), and updates memory only after the write succeeds. A write `OSError` becomes `StorageUnavailable` (declared in `application/ports.py`) → 503.
- **Adapter choice:** `build_repository` in `main.py` uses `PostgresUserRepository` when `DATABASE_URL` is set, else `JsonUserRepository` (single replica only). Both implement `close()`, called on shutdown.
- **Postgres adapter:** psycopg 3 sync `ConnectionPool`, opened with `wait=False` so startup never blocks or crashes. It never creates or alters tables; on first successful connect it loads `SEED_FILE` if the table is empty (parsed via `JsonUserRepository`). If migrations haven't run, that query fails and the service stays not-ready until they have. Any `psycopg.Error`/`PoolTimeout` → `StorageUnavailable` (503); `UniqueViolation` on email → `EmailAlreadyExists` (409). Filtering, sorting and paging still happen in `UserService` over `list_all()`; pushing them into SQL would need a port change.
- **Migrations:** Alembic in `migrations/` (plain SQL via `op.execute`; SQLAlchemy is only used by Alembic, never by the app). `migrations/env.py` reads `DATABASE_URL` through `load_settings()` (tests pass `config.attributes["database_url"]` instead) and swaps in the `postgresql+psycopg://` driver. `0001` uses `IF NOT EXISTS` only to adopt tables made by the old `schema.sql`; later migrations must not. Never edit a deployed migration; add a new one, expand-then-contract.
- **Persistence:** compose runs `users-db` (postgres:17-alpine) on the `users-db-data` volume, with no host port. `users-migrate` (same image, `alembic upgrade head`) waits for its `pg_isready` healthcheck; users-svc waits for `users-migrate` to exit 0.
- **Tests:** `test_postgres_repository.py` drops the `users` and `alembic_version` tables on `TEST_DATABASE_URL` and migrates from scratch per test; never point it at real data. The other test files work on temp copies of `data/users.json` (5 users: 4 active, 1 disabled; counts in assertions depend on it). API tests share one module-scoped client, so write tests must not break later read assertions.
- **Input schemas** use `extra="forbid"`; `UserUpdateIn` requires at least one field.

-- users-svc owns this schema; no other service reads or writes it.
-- Applied on first connect and safe to re-run. Move to a migration tool
-- (e.g. Alembic) once the schema starts changing.
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    email        TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at   TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS users_created_at_idx ON users (created_at DESC);

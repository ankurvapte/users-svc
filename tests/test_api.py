"""HTTP-level tests. Requires requirements-dev.txt (FastAPI, httpx, pytest).

    pip install -r requirements-dev.txt
    pytest
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Settings load on import, so point DATA_FILE at a throwaway copy first:
# the API tests write, and must never modify the seed file.
_TMP = Path(tempfile.mkdtemp())
shutil.copy(ROOT / "data" / "users.json", _TMP / "users.json")
os.environ["DATA_FILE"] = str(_TMP / "users.json")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PRIYA = "u1b2c3d4-0001-4e5f-8a90-000000000001"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # "with" runs the lifespan startup
        yield c
    shutil.rmtree(_TMP, ignore_errors=True)


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200


def test_list_users(client):
    body = client.get("/api/v1/users?page_size=2").json()
    assert body["pagination"] == {"page": 1, "page_size": 2, "total_items": 5, "total_pages": 3}
    assert client.get("/api/v1/users", params={"status": "disabled"}).json()["pagination"]["total_items"] == 1


def test_get_user(client):
    r = client.get(f"/api/v1/users/{PRIYA}")
    assert r.status_code == 200
    assert r.json()["email"] == "priya.sharma@example.com"
    assert "X-Request-ID" in r.headers


def test_not_found_has_consistent_error(client):
    r = client.get("/api/v1/users/nope", headers={"X-Request-ID": "abc-123"})
    assert r.status_code == 404
    assert r.json() == {"error": "not_found", "message": "User 'nope' not found", "request_id": "abc-123"}


def test_create_then_duplicate(client):
    r = client.post("/api/v1/users", json={"email": "Asha@Example.com", "display_name": "Asha"})
    assert r.status_code == 201
    user = r.json()
    assert user["email"] == "asha@example.com" and user["status"] == "active"
    assert r.headers["Location"] == f"/api/v1/users/{user['id']}"
    assert client.get(r.headers["Location"]).status_code == 200

    dup = client.post("/api/v1/users", json={"email": "asha@example.com", "display_name": "Asha 2"})
    assert dup.status_code == 409
    assert dup.json()["error"] == "conflict"


def test_patch_user(client):
    r = client.patch(f"/api/v1/users/{PRIYA}", json={"status": "disabled"})
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    assert r.json()["display_name"] == "Priya Sharma"  # untouched fields are kept


def test_patch_unknown_user_is_404(client):
    assert client.patch("/api/v1/users/nope", json={"display_name": "X"}).status_code == 404


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/v1/users", {"email": "not-an-email", "display_name": "X"}),
    ("post", "/api/v1/users", {"email": "x@example.com", "display_name": "X", "password": "secret"}),
    ("patch", f"/api/v1/users/{PRIYA}", {}),
    ("patch", f"/api/v1/users/{PRIYA}", {"status": "banned"}),
])
def test_invalid_input_is_422(client, method, path, body):
    r = getattr(client, method)(path, json=body)
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"

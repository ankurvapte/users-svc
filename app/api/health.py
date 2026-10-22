"""Health endpoints used by Docker / Kubernetes (pillar 8).

- live:  is the process up? (if not, restart the container)
- ready: can it serve traffic? (if not, stop routing requests to it)
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    is_ready = request.app.state.repository.is_ready()
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "not_ready"},
    )

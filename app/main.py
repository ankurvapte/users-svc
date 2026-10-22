"""Composition root: the one place where layers are wired together.

Run locally:   uvicorn app.main:app --reload --port 8081
In container:  see Dockerfile
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import health, routes
from app.application.ports import StorageUnavailable
from app.application.use_cases import EmailAlreadyExists, UserNotFound, UserService
from app.config import load_settings
from app.domain.models import InvalidUser
from app.infrastructure.json_repository import JsonUserRepository
from app.logging_setup import configure_logging

settings = load_settings()
configure_logging(settings.service_name, settings.log_level)
logger = logging.getLogger("users")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: build infrastructure and inject it into the use cases.
    repository = JsonUserRepository(settings.data_file)
    app.state.settings = settings
    app.state.repository = repository
    app.state.user_service = UserService(repository)
    logger.info("Service started")
    yield
    # Shutdown (runs on SIGTERM): close connections, flush buffers, etc.
    logger.info("Service shutting down")


app = FastAPI(
    title="Users Service",
    version="1.0.0",
    description="User accounts and profiles API — part of the news app microservices.",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(routes.router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    # Reuse the caller's request id (from the gateway) or create one, so a
    # single request can be traced across services in the logs.
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if not request.url.path.startswith("/health"):
        logger.info(
            "request",
            extra={
                "request_id": request_id, "method": request.method, "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        )
    return response


def _error(request: Request, status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": error, "message": message, "request_id": getattr(request.state, "request_id", None)},
    )


@app.exception_handler(UserNotFound)
async def not_found_handler(request: Request, exc: UserNotFound):
    return _error(request, 404, "not_found", str(exc))


@app.exception_handler(EmailAlreadyExists)
async def conflict_handler(request: Request, exc: EmailAlreadyExists):
    return _error(request, 409, "conflict", str(exc))


@app.exception_handler(InvalidUser)
async def invalid_user_handler(request: Request, exc: InvalidUser):
    return _error(request, 422, "validation_error", str(exc))


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return _error(request, 422, "validation_error", details)


@app.exception_handler(StorageUnavailable)
async def storage_handler(request: Request, exc: StorageUnavailable):
    return _error(request, 503, "storage_unavailable", str(exc))

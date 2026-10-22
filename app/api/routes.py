"""HTTP routes for /api/v1. Thin: parse input, call a use case, shape output."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.schemas import ErrorOut, PaginationOut, UserCreateIn, UserListOut, UserOut, UserUpdateIn
from app.application.use_cases import UserFilter, UserService
from app.domain.models import UserStatus

router = APIRouter(prefix="/api/v1", tags=["users"])


def get_service(request: Request) -> UserService:
    return request.app.state.user_service


@router.get("/users", response_model=UserListOut, summary="List users")
def list_users(
    request: Request,
    status: UserStatus | None = Query(None, description="Filter by status"),
    q: str | None = Query(None, min_length=2, description="Search in email and display name"),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1),
    service: UserService = Depends(get_service),
) -> UserListOut:
    settings = request.app.state.settings
    size = min(page_size or settings.default_page_size, settings.max_page_size)
    result = service.list_users(UserFilter(status=status, query=q), page=page, page_size=size)
    return UserListOut(
        data=[UserOut.from_domain(u) for u in result.items],
        pagination=PaginationOut(
            page=result.page, page_size=result.page_size,
            total_items=result.total, total_pages=result.total_pages,
        ),
    )


@router.get(
    "/users/{user_id}", response_model=UserOut,
    responses={404: {"model": ErrorOut}}, summary="Get one user by id",
)
def get_user(user_id: str, service: UserService = Depends(get_service)) -> UserOut:
    return UserOut.from_domain(service.get_user(user_id))


@router.post(
    "/users", response_model=UserOut, status_code=201,
    responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}}, summary="Create a user",
)
def create_user(body: UserCreateIn, response: Response, service: UserService = Depends(get_service)) -> UserOut:
    user = service.create_user(email=body.email, display_name=body.display_name)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return UserOut.from_domain(user)


@router.patch(
    "/users/{user_id}", response_model=UserOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
    summary="Update a user (partial)",
)
def update_user(user_id: str, body: UserUpdateIn, service: UserService = Depends(get_service)) -> UserOut:
    return UserOut.from_domain(service.update_user(user_id, **body.model_dump(exclude_unset=True)))

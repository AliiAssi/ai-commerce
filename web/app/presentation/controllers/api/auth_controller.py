from __future__ import annotations

from fastapi import APIRouter, Depends

from app.application.iservices.iauth_service import IAuthService
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.container import Injected
from app.presentation.schemas.auth_schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    auth: IAuthService = Injected(IAuthService),
) -> TokenResponse:
    token = await auth.register(body.email, body.password)
    return TokenResponse.from_dto(token)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    auth: IAuthService = Injected(IAuthService),
) -> TokenResponse:
    token = await auth.login(body.email, body.password)
    return TokenResponse.from_dto(token)


@router.get("/me", response_model=UserResponse)
async def me(
    user: AuthenticatedUser = Depends(get_current_user),
    auth: IAuthService = Injected(IAuthService),
) -> UserResponse:
    return UserResponse.from_dto(await auth.get_me(user.id))

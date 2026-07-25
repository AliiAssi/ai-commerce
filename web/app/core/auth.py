from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.exceptions import AuthError, ForbiddenError

ADMIN_ROLE = "admin"
CUSTOMER_ROLE = "customer"
ACCESS_TOKEN_COOKIE = "access_token"


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    role: str
    email: str = ""


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    user_id: int, role: str, email: str, *, secret: str, expires_minutes: int
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, *, secret: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid authentication token") from exc
    try:
        return AuthenticatedUser(
            id=int(payload["sub"]),
            role=str(payload["role"]),
            email=str(payload.get("email", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("Invalid token payload") from exc


_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None, cookie_token: str | None
) -> str | None:
    if credentials is not None:
        return credentials.credentials
    return cookie_token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token: str | None = Cookie(default=None),
) -> AuthenticatedUser:
    token = _extract_token(credentials, access_token)
    if token is None:
        raise AuthError("Not authenticated")
    settings = get_settings()
    return decode_access_token(token, secret=settings.JWT_SECRET)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    access_token: str | None = Cookie(default=None),
) -> AuthenticatedUser | None:
    token = _extract_token(credentials, access_token)
    if token is None:
        return None
    try:
        return decode_access_token(token, secret=get_settings().JWT_SECRET)
    except AuthError:
        return None


async def require_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if user.role != ADMIN_ROLE:
        raise ForbiddenError("Admin privileges required")
    return user

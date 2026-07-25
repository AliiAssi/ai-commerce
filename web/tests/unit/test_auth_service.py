from __future__ import annotations

import pytest

from app.application.events.bus import EventBus
from app.application.services.auth_service import AuthService
from app.core.auth import decode_access_token
from app.core.config import Settings
from app.core.exceptions import AuthError, ConflictError
from tests.unit.fakes import FakeUserRepository


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://unused/unused",
        JWT_SECRET="unit-test-secret-0123456789abcdef",
        BCRYPT_ROUNDS=4,
    )


@pytest.fixture
def service(settings: Settings) -> AuthService:
    return AuthService(FakeUserRepository(), EventBus(), settings)


async def test_register_returns_working_token(service: AuthService, settings: Settings):
    token = await service.register("New.User@Example.COM", "password123")
    principal = decode_access_token(token.access_token, secret=settings.JWT_SECRET)
    assert principal.id == token.user.id
    assert principal.role == "customer"
    assert token.user.email == "new.user@example.com"


async def test_register_duplicate_email_conflicts(service: AuthService):
    await service.register("a@x.test", "password123")
    with pytest.raises(ConflictError):
        await service.register("A@X.TEST", "different-pass")


async def test_login_roundtrip_and_wrong_password(service: AuthService):
    await service.register("a@x.test", "password123")
    token = await service.login("a@x.test", "password123")
    assert token.user.email == "a@x.test"
    with pytest.raises(AuthError):
        await service.login("a@x.test", "wrong-password")
    with pytest.raises(AuthError):
        await service.login("nobody@x.test", "password123")


async def test_get_me_for_deleted_account_401(service: AuthService):
    with pytest.raises(AuthError):
        await service.get_me(12345)

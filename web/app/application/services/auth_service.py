from __future__ import annotations

from app.application.dtos.user_dto import TokenDTO, UserDTO
from app.application.events.bus import EventBus
from app.application.events.definitions import UserRegistered
from app.application.iservices.iauth_service import IAuthService
from app.core.auth import CUSTOMER_ROLE, create_access_token, hash_password, verify_password
from app.core.config import Settings
from app.core.exceptions import AuthError, ConflictError
from app.infrastructure.irepositories.iuser_repository import IUserRepository


class AuthService(IAuthService):
    def __init__(self, users: IUserRepository, events: EventBus, settings: Settings) -> None:
        self._users = users
        self._events = events
        self._settings = settings

    def _token_for(self, user: UserDTO) -> TokenDTO:
        token = create_access_token(
            user.id,
            user.role,
            user.email,
            secret=self._settings.JWT_SECRET,
            expires_minutes=self._settings.JWT_EXPIRES_MIN,
        )
        return TokenDTO(
            access_token=token, expires_in=self._settings.JWT_EXPIRES_MIN * 60, user=user
        )

    async def register(self, email: str, password: str) -> TokenDTO:
        email = email.strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise ConflictError("An account with this email already exists")
        password_hash = hash_password(password, self._settings.BCRYPT_ROUNDS)
        user = await self._users.create(email, password_hash, CUSTOMER_ROLE)
        self._events.publish(UserRegistered(user_id=user.id, email=user.email))
        return self._token_for(user)

    async def login(self, email: str, password: str) -> TokenDTO:
        credentials = await self._users.get_credentials(email.strip().lower())
        if credentials is None or not verify_password(password, credentials.password_hash):
            raise AuthError("Invalid email or password")
        user = UserDTO(
            id=credentials.id,
            email=credentials.email,
            role=credentials.role,
            created_at=credentials.created_at,
        )
        return self._token_for(user)

    # A valid token for an account that's since been deleted resolves to 401, not a crash.
    async def get_me(self, user_id: int) -> UserDTO:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("Account no longer exists")
        return user

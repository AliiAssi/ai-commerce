from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.user_dto import TokenDTO, UserDTO
from app.presentation.schemas.common import Email


class RegisterRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=72)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: UserDTO) -> UserResponse:
        return cls.model_validate(dto)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse

    @classmethod
    def from_dto(cls, dto: TokenDTO) -> TokenResponse:
        return cls(
            access_token=dto.access_token,
            token_type=dto.token_type,
            expires_in=dto.expires_in,
            user=UserResponse.from_dto(dto.user),
        )

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserDTO(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime


class UserCredentialsDTO(BaseModel):
    id: int
    email: str
    role: str
    password_hash: str
    created_at: datetime


class TokenDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserDTO

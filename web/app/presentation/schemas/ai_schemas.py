from __future__ import annotations

from pydantic import BaseModel, Field


# Deliberately no user_email field — identity is derived server-side from the signed
# session cookie, never trusted from the client.
class ChatProxyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None

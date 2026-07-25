from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.application.iservices.iai_gateway import IAIGateway
from app.core.auth import AuthenticatedUser, get_optional_user
from app.core.config import Settings
from app.core.container import container
from app.core.exceptions import error_response
from app.presentation.schemas.ai_schemas import ChatProxyRequest

router = APIRouter(prefix="/ai", tags=["ai"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # let tokens flush live through any proxy
}


@router.post("/chat")
async def chat(
    body: ChatProxyRequest,
    user: AuthenticatedUser | None = Depends(get_optional_user),
):
    settings = container.resolve(Settings)
    if not (settings.AI_SERVICE_URL and settings.INTERNAL_API_KEY):
        return error_response(503, "ai_unavailable", "The assistant is not configured.")

    gateway = container.resolve(IAIGateway)
    handle = await gateway.open_chat(body.message, body.session_id, user.email if user else None)
    return StreamingResponse(
        handle.frames,
        media_type="text/event-stream",
        headers={**_SSE_HEADERS, "X-Session-Id": handle.session_id or ""},
    )

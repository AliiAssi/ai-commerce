from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.application.dtos.chat_dto import ChatStreamEventDTO
from app.application.iservices.ichat_service import IChatService
from app.core.auth import require_internal_key
from app.core.container import container
from app.core.logging import request_id_var
from app.presentation.schemas.chat_schemas import ChatRequest, format_sse

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/chat", dependencies=[Depends(require_internal_key)])
async def chat(body: ChatRequest) -> StreamingResponse:
    service = container.resolve(IChatService)
    session = await service.resolve_session(body.session_id, body.user_email)

    async def frames() -> AsyncIterator[str]:
        try:
            async for event in service.stream_reply(session, body.message):
                yield format_sse(event)
        except Exception:
            yield format_sse(
                ChatStreamEventDTO(type="error", message="The assistant hit an unexpected error.")
            )

    headers = {
        **_SSE_HEADERS,
        "X-Session-Id": str(session.id),
        "X-Request-Id": request_id_var.get(),
    }
    return StreamingResponse(frames(), media_type="text/event-stream", headers=headers)

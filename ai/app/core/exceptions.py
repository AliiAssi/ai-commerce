from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class LLMUnavailableError(AppError):
    status_code = 503
    code = "llm_unavailable"

    def __init__(self, message: str, *, details: Any = None, retryable: bool = False) -> None:
        super().__init__(message, details=details)
        self.retryable = retryable


class ToolExecutionError(AppError):
    status_code = 500
    code = "tool_error"


class AgentLoopLimitError(AppError):
    status_code = 500
    code = "agent_loop_limit"


class SessionNotFoundError(NotFoundError):
    code = "session_not_found"


def error_response(status_code: int, code: str, message: str, details: Any = None, headers=None):
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = jsonable_encoder(details)
    return JSONResponse(body, status_code=status_code, headers=headers)

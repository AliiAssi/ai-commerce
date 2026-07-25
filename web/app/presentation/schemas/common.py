from __future__ import annotations

from typing import Annotated, Any

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel


# Like EmailStr, but accepts reserved domains (.test etc.) so demo accounts can log in.
def _validate_email(value: str) -> str:
    try:
        result = validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized


Email = Annotated[str, AfterValidator(_validate_email)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> Page[T]:
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size if total else 0,
        )


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody

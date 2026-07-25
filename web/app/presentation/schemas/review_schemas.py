from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.application.dtos.review_dto import ReviewDTO


class CreateReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=2000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    user_id: int
    user_email: str
    rating: int
    text: str
    created_at: datetime

    @classmethod
    def from_dto(cls, dto: ReviewDTO) -> ReviewResponse:
        return cls.model_validate(dto)

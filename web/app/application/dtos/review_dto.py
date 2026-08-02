from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ReviewDTO(BaseModel):
    id: int
    product_id: int
    user_id: int
    user_email: str
    rating: int
    text: str
    created_at: datetime


class ReviewIneligibility(StrEnum):
    NOT_AUTHENTICATED = "not_authenticated"
    NOT_PURCHASED = "not_purchased"
    ALREADY_REVIEWED = "already_reviewed"


class ReviewEligibilityDTO(BaseModel):
    can_review: bool
    reason: ReviewIneligibility | None = None
    review: ReviewDTO | None = None

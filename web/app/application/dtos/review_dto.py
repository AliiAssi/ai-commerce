from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReviewDTO(BaseModel):
    id: int
    product_id: int
    user_id: int
    user_email: str
    rating: int
    text: str
    created_at: datetime

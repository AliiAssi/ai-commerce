from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class UserRegistered:
    user_id: int
    email: str


@dataclass(frozen=True)
class OrderPlaced:
    order_id: int
    user_id: int
    total: Decimal


@dataclass(frozen=True)
class OrderCancelled:
    order_id: int
    user_id: int


@dataclass(frozen=True)
class ReviewCreated:
    review_id: int
    product_id: int
    user_id: int

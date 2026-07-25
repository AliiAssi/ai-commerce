from __future__ import annotations

import logging

from app.application.events.bus import EventBus
from app.application.events.definitions import (
    OrderCancelled,
    OrderPlaced,
    ReviewCreated,
    UserRegistered,
)

logger = logging.getLogger(__name__)


def register_handlers(bus: EventBus) -> None:
    bus.subscribe(UserRegistered, _on_user_registered)
    bus.subscribe(OrderPlaced, _on_order_placed)
    bus.subscribe(OrderCancelled, _on_order_cancelled)
    bus.subscribe(ReviewCreated, _on_review_created)


def _on_user_registered(event: UserRegistered) -> None:
    logger.info("event user_registered user_id=%s", event.user_id)


def _on_order_placed(event: OrderPlaced) -> None:
    logger.info(
        "event order_placed order_id=%s user_id=%s total=%s",
        event.order_id,
        event.user_id,
        event.total,
    )


def _on_order_cancelled(event: OrderCancelled) -> None:
    logger.info("event order_cancelled order_id=%s user_id=%s", event.order_id, event.user_id)


# AI review-summary cache invalidation will hook in here later.
def _on_review_created(event: ReviewCreated) -> None:
    logger.info(
        "event review_created review_id=%s product_id=%s", event.review_id, event.product_id
    )

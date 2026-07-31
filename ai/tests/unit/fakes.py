from __future__ import annotations

import uuid
import zlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.application.dtos.chat_dto import ChatMessageDTO, ChatSessionDTO
from app.application.dtos.search_params import ProductSearchParams
from app.application.dtos.store_read_dto import (
    CategoryProductCountDTO,
    CategoryReadDTO,
    OrderItemReadDTO,
    OrderReadDTO,
    ProductPageDTO,
    ProductReadDTO,
    ReviewReadDTO,
    StoreStatsDTO,
)
from app.application.llm.iembedding_client import (
    EmbeddingBatch,
    EmbeddingError,
    IEmbeddingClient,
)
from app.application.llm.illm_client import ILLMClient
from app.application.llm.llm_dtos import (
    LLMMessageDTO,
    LLMReplyDTO,
    LLMStreamEventDTO,
    LLMToolCallDTO,
    LLMUsageDTO,
)
from app.infrastructure.irepositories.ichat_repository import IChatRepository
from app.infrastructure.irepositories.iorder_read_repository import IOrderReadRepository
from app.infrastructure.irepositories.iproduct_read_repository import IProductReadRepository
from app.infrastructure.irepositories.ireview_read_repository import IReviewReadRepository

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FakeProductReadRepository(IProductReadRepository):
    def __init__(self) -> None:
        self._products: list[ProductReadDTO] = []
        self._seq = 0

    def seed(
        self,
        name: str,
        *,
        price: str = "10.00",
        stock: int = 10,
        category: str = "Gear",
        category_slug: str = "gear",
        rating_avg: str = "0.00",
        review_count: int = 0,
        description: str = "",
        origin: str | None = None,
    ) -> ProductReadDTO:
        self._seq += 1
        product = ProductReadDTO(
            id=self._seq,
            name=name,
            description=description or f"{name} description",
            origin=origin,
            price=Decimal(price),
            stock=stock,
            category=category,
            category_slug=category_slug,
            image_url=None,
            rating_avg=Decimal(rating_avg),
            review_count=review_count,
            created_at=_EPOCH + timedelta(days=self._seq),
        )
        self._products.append(product)
        return product

    async def search(self, params: ProductSearchParams) -> ProductPageDTO:
        rows = list(self._products)
        if params.query:
            needle = params.query.lower()
            rows = [p for p in rows if needle in f"{p.name} {p.description}".lower()]
        if params.category_slug:
            rows = [p for p in rows if p.category_slug == params.category_slug]
        if params.min_price is not None:
            rows = [p for p in rows if p.price >= Decimal(str(params.min_price))]
        if params.max_price is not None:
            rows = [p for p in rows if p.price <= Decimal(str(params.max_price))]
        if params.in_stock_only:
            rows = [p for p in rows if p.stock > 0]

        if params.sort == "price_asc":
            rows.sort(key=lambda p: p.price)
        elif params.sort == "price_desc":
            rows.sort(key=lambda p: p.price, reverse=True)
        elif params.sort == "newest":
            rows.sort(key=lambda p: p.created_at, reverse=True)
        else:
            rows.sort(key=lambda p: (p.rating_avg, p.review_count), reverse=True)

        total = len(rows)
        start = (params.page - 1) * params.page_size
        return ProductPageDTO(
            items=rows[start : start + params.page_size],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def by_ids(self, product_ids) -> list[ProductReadDTO]:
        found = {p.id: p for p in self._products}
        return [found[pid] for pid in product_ids if pid in found]

    async def get(self, product_id: int) -> ProductReadDTO | None:
        return next((p for p in self._products if p.id == product_id), None)

    async def list_categories(self) -> list[CategoryReadDTO]:
        by_slug: dict[str, CategoryReadDTO] = {}
        for index, product in enumerate(self._products):
            existing = by_slug.get(product.category_slug)
            if existing is None:
                by_slug[product.category_slug] = CategoryReadDTO(
                    id=index + 1,
                    name=product.category,
                    slug=product.category_slug,
                    product_count=1,
                )
            else:
                existing.product_count += 1
        return sorted(by_slug.values(), key=lambda c: c.name)

    async def top_rated(self, limit: int) -> list[ProductReadDTO]:
        rated = [p for p in self._products if p.review_count > 0]
        rated.sort(key=lambda p: (p.rating_avg, p.review_count), reverse=True)
        return rated[:limit]

    async def low_stock(self, limit: int) -> list[ProductReadDTO]:
        return sorted(self._products, key=lambda p: (p.stock, p.id))[:limit]

    async def stats(self) -> StoreStatsDTO:
        prices = [p.price for p in self._products]
        categories = await self.list_categories()
        top = sorted(categories, key=lambda c: (-c.product_count, c.name))[:5]
        return StoreStatsDTO(
            product_count=len(self._products),
            category_count=len(categories),
            price_min=min(prices, default=None),
            price_max=max(prices, default=None),
            price_avg=(sum(prices) / len(prices)).quantize(Decimal("0.01")) if prices else None,
            top_categories=[
                CategoryProductCountDTO(name=c.name, slug=c.slug, product_count=c.product_count)
                for c in top
            ],
        )


class FakeOrderReadRepository(IOrderReadRepository):
    def __init__(self) -> None:
        self._orders: list[OrderReadDTO] = []
        self._seq = 0

    def seed(
        self,
        user_email: str,
        *,
        status: str = "paid",
        items: list[OrderItemReadDTO] | None = None,
    ) -> OrderReadDTO:
        self._seq += 1
        items = items or [
            OrderItemReadDTO(
                product_id=1, product_name="Item", unit_price=Decimal("10.00"), quantity=1
            )
        ]
        total = sum((it.unit_price * it.quantity for it in items), Decimal("0.00"))
        order = OrderReadDTO(
            id=self._seq,
            user_email=user_email,
            status=status,
            total=total,
            created_at=_EPOCH + timedelta(days=self._seq),
            updated_at=_EPOCH + timedelta(days=self._seq),
            items=items,
        )
        self._orders.append(order)
        return order

    async def get(self, order_id: int, user_email: str | None = None) -> OrderReadDTO | None:
        for order in self._orders:
            if order.id != order_id:
                continue
            if user_email is not None and order.user_email.lower() != user_email.strip().lower():
                return None
            return order
        return None

    async def list_for_user(self, user_email: str, limit: int) -> list[OrderReadDTO]:
        matches = [o for o in self._orders if o.user_email.lower() == user_email.strip().lower()]
        matches.sort(key=lambda o: (o.created_at, o.id), reverse=True)
        return matches[:limit]


class FakeReviewReadRepository(IReviewReadRepository):
    def __init__(self) -> None:
        self._by_product: dict[int, list[ReviewReadDTO]] = {}

    def seed(self, product_id: int, *, rating: int = 5, text: str = "Great") -> None:
        self._by_product.setdefault(product_id, []).append(
            ReviewReadDTO(rating=rating, text=text, created_at=_EPOCH)
        )

    async def list_for_product(self, product_id: int, limit: int) -> list[ReviewReadDTO]:
        return self._by_product.get(product_id, [])[:limit]


class FakeChatRepository(IChatRepository):
    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, ChatSessionDTO] = {}
        self._messages: dict[uuid.UUID, list[ChatMessageDTO]] = {}

    async def create_session(self, user_email: str | None) -> ChatSessionDTO:
        session = ChatSessionDTO(id=uuid.uuid4(), user_email=user_email)
        self._sessions[session.id] = session
        self._messages[session.id] = []
        return session

    async def get_session(self, session_id: uuid.UUID) -> ChatSessionDTO | None:
        return self._sessions.get(session_id)

    async def list_messages(self, session_id: uuid.UUID) -> list[ChatMessageDTO]:
        return list(self._messages.get(session_id, []))

    async def count_messages(self, session_id: uuid.UUID) -> int:
        return len(self._messages.get(session_id, []))

    async def append_messages(self, session_id: uuid.UUID, messages: list[ChatMessageDTO]) -> None:
        self._messages.setdefault(session_id, []).extend(messages)


@dataclass
class FakeTurn:
    text: str = ""
    tool_calls: list[LLMToolCallDTO] = field(default_factory=list)


def tool_turn(name: str, **arguments: Any) -> FakeTurn:
    return FakeTurn(tool_calls=[LLMToolCallDTO(name=name, arguments=arguments)])


def answer_turn(text: str) -> FakeTurn:
    return FakeTurn(text=text)


class FakeLLMClient(ILLMClient):
    def __init__(self, script: list[FakeTurn]) -> None:
        self._script = list(script)
        self.calls: list[list[LLMMessageDTO]] = []

    def _next(self, messages: list[LLMMessageDTO]) -> FakeTurn:
        self.calls.append(list(messages))
        return self._script.pop(0) if self._script else FakeTurn(text="")

    async def chat(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> LLMReplyDTO:
        turn = self._next(messages)
        return LLMReplyDTO(
            content=turn.text,
            tool_calls=turn.tool_calls,
            usage=LLMUsageDTO(prompt_tokens=1, completion_tokens=1, duration_ms=1.0),
        )

    async def stream(
        self, messages: list[LLMMessageDTO], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMStreamEventDTO]:
        turn = self._next(messages)
        for call in turn.tool_calls:
            yield LLMStreamEventDTO(type="tool_call", tool_call=call)
        for word in turn.text.split():
            yield LLMStreamEventDTO(type="token", text=word + " ")
        yield LLMStreamEventDTO(
            type="done",
            usage=LLMUsageDTO(prompt_tokens=1, completion_tokens=1, duration_ms=1.0),
        )


class FakeEmbeddingClient(IEmbeddingClient):
    def __init__(
        self,
        *,
        model: str = "fake-embedding-001",
        dimensions: int = 768,
        fail_with: EmbeddingError | None = None,
        fail_times: int | None = None,
        width_override: int | None = None,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._fail_with = fail_with
        self._fail_times = fail_times
        self._width_override = width_override
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def set_failure(self, error: EmbeddingError | None, *, times: int | None = None) -> None:
        self._fail_with = error
        self._fail_times = times

    def _maybe_fail(self) -> None:
        if self._fail_with is None:
            return
        if self._fail_times is None:
            raise self._fail_with
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._fail_with

    def _vector(self, text: str) -> tuple[float, ...]:
        width = self._width_override or self._dimensions
        buckets = [0.0] * width
        for token in text.lower().split():
            buckets[hash_token(token) % width] += 1.0
        norm = sum(value * value for value in buckets) ** 0.5
        if not norm:
            buckets[0] = 1.0
            norm = 1.0
        return tuple(value / norm for value in buckets)

    async def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.document_calls.append(list(texts))
        self._maybe_fail()
        return EmbeddingBatch(
            vectors=tuple(self._vector(text) for text in texts),
            model=self._model,
            dimensions=self._width_override or self._dimensions,
        )

    async def embed_query(self, text: str) -> EmbeddingBatch:
        self.query_calls.append(text)
        self._maybe_fail()
        return EmbeddingBatch(
            vectors=(self._vector(text),),
            model=self._model,
            dimensions=self._width_override or self._dimensions,
        )


def hash_token(token: str) -> int:
    return zlib.crc32(token.encode("utf-8"))

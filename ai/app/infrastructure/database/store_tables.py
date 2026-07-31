from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import TSVECTOR

store_metadata = MetaData()

user_role = postgresql.ENUM("customer", "admin", name="user_role", create_type=False)
order_status = postgresql.ENUM(
    "paid", "shipped", "delivered", "cancelled", name="order_status", create_type=False
)

categories = Table(
    "categories",
    store_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("slug", String(100), nullable=False),
)

users = Table(
    "users",
    store_metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(320), nullable=False),
    Column("password_hash", String(128), nullable=False),
    Column("role", user_role, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

products = Table(
    "products",
    store_metadata,
    Column("id", Integer, primary_key=True),
    Column("category_id", Integer, nullable=False),
    Column("name", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("origin", String(80)),
    Column("price", Numeric(10, 2), nullable=False),
    Column("stock", Integer, nullable=False),
    Column("image_url", String(500)),
    Column("rating_avg", Numeric(3, 2), nullable=False),
    Column("review_count", Integer, nullable=False),
    Column("is_archived", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("search_vector", TSVECTOR),
)

orders = Table(
    "orders",
    store_metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False),
    Column("status", order_status, nullable=False),
    Column("total", Numeric(10, 2), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

order_items = Table(
    "order_items",
    store_metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, nullable=False),
    Column("product_id", Integer, nullable=False),
    Column("product_name", String(200), nullable=False),
    Column("unit_price", Numeric(10, 2), nullable=False),
    Column("quantity", Integer, nullable=False),
)

reviews = Table(
    "reviews",
    store_metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, nullable=False),
    Column("user_id", Integer, nullable=False),
    Column("rating", SmallInteger, nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

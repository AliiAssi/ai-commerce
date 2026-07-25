from __future__ import annotations

from app.core.config import _normalize_database_url


def test_postgres_scheme_becomes_asyncpg() -> None:
    url, connect_args = _normalize_database_url("postgresql://u:p@host:5432/db")
    assert url == "postgresql+asyncpg://u:p@host:5432/db"
    assert connect_args == {}


def test_sslmode_moves_to_connect_args() -> None:
    url, connect_args = _normalize_database_url(
        "postgres://u:p@host/db?sslmode=require&channel_binding=require"
    )
    assert url == "postgresql+asyncpg://u:p@host/db"
    assert connect_args == {"ssl": "require"}


def test_unknown_sslmode_falls_back_to_require() -> None:
    _, connect_args = _normalize_database_url("postgres://u:p@host/db?sslmode=bogus")
    assert connect_args == {"ssl": "require"}

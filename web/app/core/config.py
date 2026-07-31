from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ASYNCPG_SSL_MODES = {"prefer", "allow", "require", "verify-ca", "verify-full"}

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class DatabaseSettings(BaseSettings):
    """Everything a schema migration needs, and deliberately nothing else.

    Alembic's env.py builds one of these rather than the full `Settings`. A migration touches
    the database and nothing but the database, so requiring an LLM API key or a JWT secret to
    run one couples schema management to application config it never reads — and every new
    required setting silently becomes a new way for migrations to fail.

    That is not hypothetical: it broke CI the first time CI ever ran this branch. It went
    unnoticed for five phases because the repo-root `.env` fills every gap on a developer's
    machine, so a local `alembic upgrade head` can never reproduce what CI actually has.
    """

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = Field(min_length=1)

    @property
    def sqlalchemy_database_url(self) -> str:
        url, _ = _normalize_database_url(self.DATABASE_URL)
        return url

    @property
    def database_connect_args(self) -> dict[str, Any]:
        _, connect_args = _normalize_database_url(self.DATABASE_URL)
        return connect_args


class Settings(DatabaseSettings):
    JWT_SECRET: str = Field(min_length=32)
    JWT_EXPIRES_MIN: int = 1440
    BCRYPT_ROUNDS: int = 12
    ENVIRONMENT: Literal["development", "production"] = "development"

    AI_SERVICE_URL: str = ""
    INTERNAL_API_KEY: str = ""

    STORE_NAME: str = "BEIT"

    SEED_ADMIN_EMAIL: str = "admin@store.test"
    SEED_ADMIN_PASSWORD: str = "Admin#12345"

    LOW_STOCK_THRESHOLD: int = 5

    #  Smart search
    SMART_SEARCH_ROUTING_ENABLED: bool = False
    # The outermost limit on a storefront search, and the only one that is actually enforced end
    # to end: when this expires the gateway returns None and web serves its own lexical results,
    # which is a real quality drop rather than a formality. It therefore has to exceed everything
    # the AI service may spend — query embedding (2 s cap, ~434 ms p50) plus retrieval plus
    # RERANKER_TIMEOUT_SECONDS, which is 5 s. Set below that and raising the reranker's budget
    # buys nothing: the gateway would abandon the request before the reranker ever answered.
    SEARCH_TIMEOUT_SECONDS: float = Field(default=8.0, gt=0)

    @model_validator(mode="after")
    def _check_smart_search(self) -> Settings:
        if self.SMART_SEARCH_ROUTING_ENABLED and not self.AI_SERVICE_URL:
            raise ValueError(
                "SMART_SEARCH_ROUTING_ENABLED requires AI_SERVICE_URL: "
                "the AI service owns retrieval."
            )
        return self


def _normalize_database_url(raw: str) -> tuple[str, dict[str, Any]]:
    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k not in ("sslmode", "channel_binding")]
    sslmode = next((v for k, v in pairs if k == "sslmode"), None)

    connect_args: dict[str, Any] = {}
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = sslmode if sslmode in _ASYNCPG_SSL_MODES else "require"

    url = urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
    return url, connect_args


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_settings_or_exit() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        problems = [
            f"{err['loc'][0]}: {err['msg']}" if err["loc"] else err["msg"] for err in exc.errors()
        ]
        sys.exit(
            "FATAL: missing/invalid environment variables:\n  "
            + "\n  ".join(problems)
            + f"\nSet them in {ENV_FILE} (copy .env.example at the repo root)."
        )


def get_migration_settings() -> DatabaseSettings:
    """Settings for Alembic. Fails on a missing DATABASE_URL and on nothing else."""
    try:
        return DatabaseSettings()
    except ValidationError:
        sys.exit(
            "FATAL: DATABASE_URL is required to run migrations.\n"
            f"Set it in the environment or in {ENV_FILE}."
        )

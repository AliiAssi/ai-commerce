from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.vector_schema import EMBEDDING_VECTOR_DIMENSIONS

_ASYNCPG_SSL_MODES = {"prefer", "allow", "require", "verify-ca", "verify-full"}

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class DatabaseSettings(BaseSettings):
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
    ENVIRONMENT: Literal["development", "production"] = "development"

    INTERNAL_API_KEY: str = Field(min_length=16)
    MCP_BEARER_TOKEN: str = Field(min_length=16)

    LLM_PROVIDER: Literal["ollama"] = "ollama"
    OLLAMA_API_KEY: str = Field(min_length=1)
    OLLAMA_MODEL: str = "gemma4:31b-cloud"
    OLLAMA_HOST: str = "https://ollama.com"

    MAX_TOOL_ITERATIONS: int = 5
    MAX_TOKENS_PER_REPLY: int = 1024
    MAX_MESSAGES_PER_SESSION: int = 40
    LLM_TIMEOUT_SECONDS: float = 60.0

    STORE_NAME: str = "BEIT"

    SMART_SEARCH_ENABLED: bool = False

    EMBEDDING_PROVIDER: str = ""
    EMBEDDING_HOST: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_DIMENSIONS: int | None = None
    EMBEDDING_TIMEOUT_SECONDS: float = 2.0

    EMBEDDING_FALLBACK_PROVIDER: str = ""
    EMBEDDING_FALLBACK_HOST: str = ""
    EMBEDDING_FALLBACK_API_KEY: str = ""
    EMBEDDING_FALLBACK_MODEL: str = ""

    EMBEDDING_BREAKER_FAILURES: int = Field(default=3, ge=1)
    EMBEDDING_BREAKER_RESET_SECONDS: float = Field(default=30.0, gt=0)

    RERANKER_PROVIDER: str = ""
    RERANKER_HOST: str = ""
    RERANKER_API_KEY: str = ""
    RERANKER_MODEL: str = ""
    RERANKER_TOP_K: int = Field(default=30, ge=20, le=50)
    RERANKER_TIMEOUT_SECONDS: float = 5

    RERANKER_FALLBACK_PROVIDER: str = ""
    RERANKER_FALLBACK_HOST: str = ""
    RERANKER_FALLBACK_API_KEY: str = ""
    RERANKER_FALLBACK_MODEL: str = ""

    RERANKER_BREAKER_FAILURES: int = Field(default=3, ge=1)
    RERANKER_BREAKER_RESET_SECONDS: float = Field(default=30.0, gt=0)

    RERANKER_QUOTA_COOLDOWN_SECONDS: float = Field(default=900.0, gt=0)

    SEARCH_DEADLINE_SECONDS: float = 30.0
    SEARCH_SEMANTIC_CANDIDATES: int = Field(default=100, ge=1, le=1000)
    SEARCH_LEXICAL_CANDIDATES: int = Field(default=100, ge=1, le=1000)
    SEARCH_TRIGRAM_CANDIDATES: int = Field(default=50, ge=0, le=1000)
    SEARCH_TRIGRAM_THRESHOLD: float = Field(default=0.3, ge=0.0, le=1.0)
    SEARCH_RRF_K: int = Field(default=60, ge=1)
    SEARCH_RRF_WEIGHT_SEMANTIC: float = Field(default=1.0, ge=0.0)
    SEARCH_RRF_WEIGHT_LEXICAL: float = Field(default=1.0, ge=0.0)
    SEARCH_RRF_WEIGHT_TRIGRAM: float = Field(default=0.5, ge=0.0)
    SEARCH_RELEVANCE_FLOOR: float = Field(default=0.0, ge=0.0)

    SEARCH_SEMANTIC_MIN_SIMILARITY: float = Field(default=0.645, ge=0.0, le=1.0)

    SEARCH_HNSW_EF_SEARCH: int = Field(default=100, ge=1, le=1000)
    SEARCH_HNSW_ITERATIVE_SCAN: str = Field(default="relaxed_order")

    SEARCH_LEXICAL_WEIGHT_NAME: float = Field(default=1.0, ge=0.0, le=1.0)
    SEARCH_LEXICAL_WEIGHT_FACET: float = Field(default=0.4, ge=0.0, le=1.0)
    SEARCH_LEXICAL_WEIGHT_DESCRIPTION: float = Field(default=0.1, ge=0.0, le=1.0)

    SEARCH_INDEX_WORKER_ENABLED: bool = True
    SEARCH_INDEX_SWEEP_SECONDS: float = Field(default=20.0, gt=0)
    SEARCH_INDEX_BATCH_SIZE: int = Field(default=16, ge=1, le=256)
    SEARCH_INDEX_POLL_SECONDS: float = Field(default=5.0, gt=0)
    SEARCH_INDEX_LEASE_SECONDS: int = Field(default=120, ge=1)
    SEARCH_INDEX_MAX_ATTEMPTS: int = Field(default=5, ge=1)
    SEARCH_INDEX_BACKOFF_CAP_SECONDS: float = Field(default=300.0, gt=0)
    SEARCH_INDEX_SHUTDOWN_SECONDS: float = Field(default=10.0, gt=0)
    SEARCH_INDEX_MIN_COVERAGE: float = Field(default=0.95, ge=0.0, le=1.0)

    SEARCH_QUERY_CACHE_TTL_SECONDS: int = Field(default=86_400, ge=0)
    SEARCH_QUERY_CACHE_PRUNE_SECONDS: float = Field(default=3600.0, gt=0)
    SEARCH_EVENT_QUERY_RETENTION_DAYS: int = Field(default=30, ge=1)
    SEARCH_EVENT_METRIC_RETENTION_DAYS: int = Field(default=365, ge=1)

    MCP_ALLOWED_HOSTS: str = ""
    MCP_ALLOWED_ORIGINS: str = ""
    RENDER_EXTERNAL_HOSTNAME: str = ""

    @model_validator(mode="after")
    def _check_smart_search(self) -> Settings:
        if self.SMART_SEARCH_ENABLED:
            missing = [
                name
                for name in (
                    "EMBEDDING_PROVIDER",
                    "EMBEDDING_MODEL",
                    "EMBEDDING_DIMENSIONS",
                    "EMBEDDING_API_KEY",
                )
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    f"SMART_SEARCH_ENABLED requires {', '.join(missing)}. "
                    "Choose and benchmark an embedding model first."
                )
            if self.EMBEDDING_DIMENSIONS != EMBEDDING_VECTOR_DIMENSIONS:
                raise ValueError(
                    f"EMBEDDING_DIMENSIONS={self.EMBEDDING_DIMENSIONS} does not match the "
                    f"vector({EMBEDDING_VECTOR_DIMENSIONS}) columns this schema was migrated "
                    "with. Changing the width needs a migration and a full re-embed, not a "
                    "settings change."
                )
            fallback = (
                self.EMBEDDING_FALLBACK_PROVIDER,
                self.EMBEDDING_FALLBACK_MODEL,
                self.EMBEDDING_FALLBACK_API_KEY,
            )
            if any(fallback) and not all(fallback):
                raise ValueError(
                    "EMBEDDING_FALLBACK_PROVIDER, EMBEDDING_FALLBACK_MODEL and "
                    "EMBEDDING_FALLBACK_API_KEY must be set together or not at all."
                )
        if self.SEARCH_HNSW_ITERATIVE_SCAN not in ("off", "relaxed_order", "strict_order"):
            raise ValueError(
                "SEARCH_HNSW_ITERATIVE_SCAN must be one of off, relaxed_order, strict_order; "
                f"got {self.SEARCH_HNSW_ITERATIVE_SCAN!r}"
            )
        if self.RERANKER_TIMEOUT_SECONDS > self.SEARCH_DEADLINE_SECONDS:
            raise ValueError(
                "RERANKER_TIMEOUT_SECONDS must not exceed SEARCH_DEADLINE_SECONDS "
                f"({self.RERANKER_TIMEOUT_SECONDS} > {self.SEARCH_DEADLINE_SECONDS})"
            )
        if self.SEARCH_EVENT_QUERY_RETENTION_DAYS > self.SEARCH_EVENT_METRIC_RETENTION_DAYS:
            raise ValueError(
                "SEARCH_EVENT_QUERY_RETENTION_DAYS must not exceed "
                "SEARCH_EVENT_METRIC_RETENTION_DAYS: redacted query text is dropped no later "
                "than the aggregate metrics derived from it"
            )
        return self

    @property
    def mcp_allowed_hosts(self) -> list[str]:
        hosts = _split_csv(self.MCP_ALLOWED_HOSTS)
        if self.RENDER_EXTERNAL_HOSTNAME:
            hosts.append(self.RENDER_EXTERNAL_HOSTNAME)
        return hosts

    @property
    def mcp_allowed_origins(self) -> list[str]:
        origins = _split_csv(self.MCP_ALLOWED_ORIGINS)
        if self.RENDER_EXTERNAL_HOSTNAME:
            origins.append(f"https://{self.RENDER_EXTERNAL_HOSTNAME}")
        return origins


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
    try:
        return DatabaseSettings()
    except ValidationError:
        sys.exit(
            "FATAL: DATABASE_URL is required to run migrations.\n"
            f"Set it in the environment or in {ENV_FILE}."
        )

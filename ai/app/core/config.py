from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

_ASYNCPG_SSL_MODES = {"prefer", "allow", "require", "verify-ca", "verify-full"}

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = Field(min_length=1)
    ENVIRONMENT: Literal["development", "production"] = "development"

    # We have 2 separate edges: REST (Web -> AI) and /mcp (external clients).
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

    MCP_ALLOWED_HOSTS: str = ""
    MCP_ALLOWED_ORIGINS: str = ""
    RENDER_EXTERNAL_HOSTNAME: str = ""

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

    @property
    def sqlalchemy_database_url(self) -> str:
        url, _ = _normalize_database_url(self.DATABASE_URL)
        return url

    @property
    def database_connect_args(self) -> dict[str, Any]:
        _, connect_args = _normalize_database_url(self.DATABASE_URL)
        return connect_args


# asyncpg rejects libpq's sslmode/channel_binding params — strip them, pass ssl separately.
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


# Called at startup so a missing env var fails with a readable message, not a stack trace.
def load_settings_or_exit() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        missing = ", ".join(str(err["loc"][0]) for err in exc.errors())
        sys.exit(
            f"FATAL: missing/invalid required environment variables: {missing}.\n"
            f"Set them in {ENV_FILE} (copy .env.example at the repo root)."
        )

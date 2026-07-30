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

    #  Smart search
    #
    # This service owns retrieval, so the models live here beside the chat model. Everything is
    # inert while SMART_SEARCH_ENABLED is false, which is the default.
    #
    # The reranker block is deliberately empty: it is picked by measuring candidates against a
    # fixed relevance corpus, against the phase-6 baseline this phase establishes.
    SMART_SEARCH_ENABLED: bool = False

    EMBEDDING_PROVIDER: str = ""
    EMBEDDING_HOST: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""
    # Validated against EMBEDDING_VECTOR_DIMENSIONS below rather than free: the width is baked
    # into `vector(n)` and cannot be changed without a migration and a full re-embed.
    EMBEDDING_DIMENSIONS: int | None = None
    EMBEDDING_TIMEOUT_SECONDS: float = 2.0

    # A second provider, embedded into its own column so failover costs no correctness.
    #
    # The chosen primary is a free tier whose quota and model availability can change without
    # notice, and §12 requires embedding failure to degrade rather than fail. A breaker that can
    # only degrade to lexical is strictly worse than one that can reach a second provider — but
    # only if the query and the documents it is compared against came from the *same* model, so
    # the fallback embeds its own column rather than querying the primary's.
    #
    # There is no separate dimensions setting. Both columns are vector(EMBEDDING_DIMENSIONS), so
    # a fallback at another width could not be stored.
    EMBEDDING_FALLBACK_PROVIDER: str = ""
    EMBEDDING_FALLBACK_HOST: str = ""
    EMBEDDING_FALLBACK_API_KEY: str = ""
    EMBEDDING_FALLBACK_MODEL: str = ""

    # Circuit breaker, per provider and independent of the reranker's (§12). Opening after a run
    # of failures is what stops every query paying the same timeout; the probe interval is what
    # closes it again without an operator.
    EMBEDDING_BREAKER_FAILURES: int = Field(default=3, ge=1)
    EMBEDDING_BREAKER_RESET_SECONDS: float = Field(default=30.0, gt=0)

    RERANKER_PROVIDER: str = ""
    RERANKER_HOST: str = ""
    RERANKER_API_KEY: str = ""
    RERANKER_MODEL: str = ""
    RERANKER_TOP_K: int = Field(default=30, ge=20, le=50)
    RERANKER_TIMEOUT_SECONDS: float = 1.5

    # Retrieval shape. Candidate counts are per leg before fusion, so the fused set is smaller
    # than their sum. The floor stays at 0.0 until it has been calibrated against the relevance
    # corpus — a guessed floor would silently drop good results.
    SEARCH_DEADLINE_SECONDS: float = 3.0
    SEARCH_SEMANTIC_CANDIDATES: int = Field(default=100, ge=1, le=1000)
    SEARCH_LEXICAL_CANDIDATES: int = Field(default=100, ge=1, le=1000)
    SEARCH_TRIGRAM_CANDIDATES: int = Field(default=50, ge=0, le=1000)
    SEARCH_TRIGRAM_THRESHOLD: float = Field(default=0.3, ge=0.0, le=1.0)
    SEARCH_RRF_K: int = Field(default=60, ge=1)
    SEARCH_RRF_WEIGHT_SEMANTIC: float = Field(default=1.0, ge=0.0)
    SEARCH_RRF_WEIGHT_LEXICAL: float = Field(default=1.0, ge=0.0)
    SEARCH_RRF_WEIGHT_TRIGRAM: float = Field(default=0.5, ge=0.0)
    SEARCH_RELEVANCE_FLOOR: float = Field(default=0.0, ge=0.0)

    # §7.4's "empty set instead of unrelated nearest neighbors", applied where it can actually
    # work: on cosine similarity, inside the semantic leg.
    #
    # SEARCH_RELEVANCE_FLOOR cannot do this job alone and never could. RRF scores a leg's best
    # result at weight/(k+1) whatever that result is, so `zzzznotathing`'s nearest neighbour
    # arrives at rank 1 with exactly the same fused score a perfect match would earn. Rank
    # carries no notion of "and this one is bad". Only a similarity threshold does — and the
    # semantic leg has to admit candidates no other leg found, or Arabic gains nothing, since
    # Arabic has no lexical leg at all (§2.1).
    #
    # Calibrated against the §15 corpus on 2026-07-29, not guessed. Every gating case passes for
    # any value in (0.6344, 0.6562]; 0.645 is the midpoint, ~0.011 clear of both edges.
    #
    #   0.6344  the highest similarity any excluded product reaches — `ar-not-in-catalog`
    #           (ماكينة قهوة كهربائية) scoring Hammered Copper Rakwe. Below this the hard
    #           negatives leak.
    #   0.6562  the lowest similarity a required product reaches with no other leg to find it —
    #           `ar-sour-for-fattoush` (شيء حامض للفتوش) scoring Pomegranate Molasses. Above this
    #           Arabic recall breaks.
    #
    # Both edges are Arabic, in both directions. `en-nonsense` and `en-not-in-catalog` clear at
    # 0.5915 and 0.5984, so English never constrains this value — the same asymmetry the phase-5
    # baseline found, from the other side.
    #
    # This number is a property of `gemini-embedding-001` at 768 dimensions. Similarity scales
    # differ between models, so changing EMBEDDING_MODEL means measuring this again.
    SEARCH_SEMANTIC_MIN_SIMILARITY: float = Field(default=0.645, ge=0.0, le=1.0)

    # HNSW's query-side knobs, which §14.3 requires to be tunable. `ef_search` trades recall for
    # latency; iterative scan is what stops a filtered query silently under-returning when the
    # approximate index hands back fewer rows than the filter needs (§7.4). `relaxed_order` keeps
    # the scan cheap — exact ordering is re-established by RRF and §7.4's tie-breakers anyway.
    SEARCH_HNSW_EF_SEARCH: int = Field(default=100, ge=1, le=1000)
    SEARCH_HNSW_ITERATIVE_SCAN: str = Field(default="relaxed_order")

    # How much each part of a document counts when the lexical leg ranks it. These multiply the
    # setweight labels the index worker stores — A on the product name, B on category and
    # origin, D on the description — and are applied per query, so retuning them costs nothing
    # and does not invalidate a single stored row. Changing which label a *field* gets is the
    # other thing entirely: that needs a DOCUMENT_VERSION bump and a full rebuild.
    SEARCH_LEXICAL_WEIGHT_NAME: float = Field(default=1.0, ge=0.0, le=1.0)
    SEARCH_LEXICAL_WEIGHT_FACET: float = Field(default=0.4, ge=0.0, le=1.0)
    SEARCH_LEXICAL_WEIGHT_DESCRIPTION: float = Field(default=0.1, ge=0.0, le=1.0)

    # The worker detects stale documents by comparing a hash of live catalog data against the
    # stored one, so the sweep interval — not a queue insert — bounds index freshness.
    SEARCH_INDEX_WORKER_ENABLED: bool = True
    SEARCH_INDEX_SWEEP_SECONDS: float = Field(default=20.0, gt=0)
    SEARCH_INDEX_BATCH_SIZE: int = Field(default=16, ge=1, le=256)
    SEARCH_INDEX_POLL_SECONDS: float = Field(default=5.0, gt=0)
    SEARCH_INDEX_LEASE_SECONDS: int = Field(default=120, ge=1)
    SEARCH_INDEX_MAX_ATTEMPTS: int = Field(default=5, ge=1)
    SEARCH_INDEX_BACKOFF_CAP_SECONDS: float = Field(default=300.0, gt=0)
    SEARCH_INDEX_SHUTDOWN_SECONDS: float = Field(default=10.0, gt=0)
    # Below this share of active products having a document, retrieval drops from §12's step 3
    # (this service's documents) to step 4 (web's products.search_vector), which is always
    # populated. Not 1.0: one product mid-reindex must not switch the whole store's search path.
    SEARCH_INDEX_MIN_COVERAGE: float = Field(default=0.95, ge=0.0, le=1.0)

    SEARCH_QUERY_CACHE_TTL_SECONDS: int = Field(default=86_400, ge=0)
    # §10.4 requires the cache to have a pruning job. It runs inside the index worker rather than
    # as a second process, on its own much longer clock: one indexed DELETE per sweep would be
    # 4,320 pointless statements a day to collect rows that live for one.
    SEARCH_QUERY_CACHE_PRUNE_SECONDS: float = Field(default=3600.0, gt=0)
    SEARCH_EVENT_QUERY_RETENTION_DAYS: int = Field(default=30, ge=1)
    SEARCH_EVENT_METRIC_RETENTION_DAYS: int = Field(default=365, ge=1)

    MCP_ALLOWED_HOSTS: str = ""
    MCP_ALLOWED_ORIGINS: str = ""
    RENDER_EXTERNAL_HOSTNAME: str = ""

    @model_validator(mode="after")
    def _check_smart_search(self) -> Settings:
        # Refusing to boot beats silently serving lexical results under a flag that claims
        # semantic search.
        #
        # This used to check only that three settings were non-empty, which stopped guarding
        # anything the moment the bake-off filled all three in: the flag could then be switched
        # on with no vector column and no bound client. What it checks now is that the
        # configuration could actually describe the schema. The other half — that the column and
        # the client really exist — needs a database and lives in main.py's boot probe.
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
                # A width that disagrees with the column would not fail at boot without this —
                # it would fail on the first write, after a whole backfill had been paid for and
                # thrown away. That is why the four embedding settings are pinned in render.yaml
                # rather than dashboard-managed.
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
                # Half-configured is worse than absent: the fallback column would be enqueued for
                # backfill on every sweep and fail every time.
                raise ValueError(
                    "EMBEDDING_FALLBACK_PROVIDER, EMBEDDING_FALLBACK_MODEL and "
                    "EMBEDDING_FALLBACK_API_KEY must be set together or not at all."
                )
        # SET LOCAL takes no bound parameters, so this value reaches SQL as text. Checking it
        # here means a typo is a boot failure rather than an error on the first semantic query.
        if self.SEARCH_HNSW_ITERATIVE_SCAN not in ("off", "relaxed_order", "strict_order"):
            raise ValueError(
                "SEARCH_HNSW_ITERATIVE_SCAN must be one of off, relaxed_order, strict_order; "
                f"got {self.SEARCH_HNSW_ITERATIVE_SCAN!r}"
            )
        # The reranker gets part of the overall search budget, never more than all of it.
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
        # Field errors carry the field name in loc; whole-model validators carry an empty loc
        # and only a message, so report the message rather than indexing into nothing.
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

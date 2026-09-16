"""Application configuration.

All runtime configuration is declared here with explicit types and defaults
(Principle 8). Nothing reads ``os.environ`` directly elsewhere in the code.
"""

from functools import lru_cache
from typing import Final

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL: Final[str] = "sqlite+aiosqlite:///./suas_local.db"
DEFAULT_WEATHER_URL: Final[str] = "https://api.open-meteo.com/v1/forecast"

# Managed Postgres providers hand out a driverless URL: Railway gives
# `postgresql://`, Heroku-style providers still give `postgres://`.
ASYNC_POSTGRES_SCHEME: Final[str] = "postgresql+psycopg://"
DRIVERLESS_POSTGRES_SCHEMES: Final[tuple[str, ...]] = ("postgresql://", "postgres://")


def describe_database_url(url: str) -> str:
    """Return a credential-free description of ``url`` for logging.

    A deployment that silently uses the wrong database is the expensive kind of
    wrong, and the cheapest guard against it is saying out loud which one was
    chosen. Credentials are stripped rather than masked in place: a log line is
    copied into issues and screenshots, so the safe thing is for the secret
    never to be on it.
    """
    scheme, separator, remainder = url.partition("://")
    if not separator:
        return scheme
    location: str = remainder.rpartition("@")[2]
    return f"{scheme}://{location}" if location else scheme


def normalise_database_url(url: str) -> str:
    """Return ``url`` with an explicit async driver when it names PostgreSQL.

    SQLAlchemy maps a bare ``postgresql://`` to psycopg2, which this project
    does not install -- so pasting a provider's URL in unchanged fails at
    startup with an import error that never mentions the URL. Worse, it is an
    async engine, and psycopg2 could not serve it even if it were installed.

    Normalising here means ``SUAS_DATABASE_URL=${{Postgres.DATABASE_URL}}``
    works as a direct reference, with no hand-edited scheme to get wrong or to
    silently revert the next time someone re-copies the variable. Anything that
    already names a driver, and every non-PostgreSQL URL, is returned untouched.
    """
    for scheme in DRIVERLESS_POSTGRES_SCHEMES:
        if url.startswith(scheme):
            return ASYNC_POSTGRES_SCHEME + url[len(scheme) :]
    return url


class Settings(BaseSettings):
    """Strongly typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SUAS_",
        extra="ignore",
        # database_url declares an explicit validation_alias, which would
        # otherwise stop Settings(database_url=...) working by field name --
        # the form the tests and every caller use.
        populate_by_name=True,
    )

    # Read SUAS_DATABASE_URL first, then the DATABASE_URL that Railway, Heroku and
    # most managed providers set by convention. Without the second name, linking a
    # Postgres service is not enough on its own and the app falls back to SQLite --
    # which is how a deployment ends up on an ephemeral file nobody chose.
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        validation_alias=AliasChoices("SUAS_DATABASE_URL", "DATABASE_URL"),
    )
    # The image sets this true (see backend/Dockerfile). SQLite is for local
    # development and the test suite; a container has no durable filesystem to put
    # it on, and on Railway it is not an option at all.
    require_postgres: bool = Field(default=False)

    @field_validator("database_url")
    @classmethod
    def _add_async_driver(cls, value: str) -> str:
        """Accept a managed provider's URL verbatim (see normalise_database_url)."""
        return normalise_database_url(value)

    @model_validator(mode="after")
    def _refuse_non_postgres_when_required(self) -> "Settings":
        """Fail at startup, by name, rather than at the first query by traceback.

        Without this the app starts on the SQLite default and dies inside
        aiosqlite with "unable to open database file" -- forty frames that never
        mention the variable that was missing. One line that names it is worth
        more than any amount of that.
        """
        if self.require_postgres and not self.uses_postgres:
            raise ValueError(
                "PostgreSQL is required here but the configured database is "
                f"{describe_database_url(self.database_url)!r}. Set SUAS_DATABASE_URL "
                "(or DATABASE_URL) to the Postgres service URL -- on Railway, "
                "reference it as ${{Postgres.DATABASE_URL}}."
            )
        return self

    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    api_key: str = Field(default="")
    cors_origins: str = Field(default="http://localhost:3000")
    weather_base_url: str = Field(default=DEFAULT_WEATHER_URL)
    # Per-request. Small, because a planning request is waiting on it.
    weather_timeout_s: float = Field(default=3.0, gt=0.0)
    weather_retry_attempts: int = Field(default=3, ge=1, le=6)
    # Hard ceiling on the whole operation. Without it, per-request timeouts
    # multiply by the retry count and the endpoint hangs for far longer than
    # any single number in this file suggests.
    weather_deadline_s: float = Field(default=6.0, gt=0.0)
    # How long a reading stays good enough to fly on.
    weather_cache_ttl_s: float = Field(default=600.0, ge=0.0)
    # Retrieval. 'hashing' needs nothing and understands nothing; 'http' calls
    # a model service such as the one in services/embeddings/.
    embedding_provider: str = Field(default="hashing", pattern="^(hashing|http)$")
    embedding_url: str = Field(default="")
    embedding_model_id: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384, ge=8, le=4096)
    embedding_timeout_s: float = Field(default=30.0, gt=0.0)
    # How many candidates each retrieval leg considers before fusion.
    retrieval_candidates: int = Field(default=20, ge=1, le=200)
    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    llm_timeout_s: float = Field(default=30.0, gt=0.0)
    llm_max_retries: int = Field(default=2, ge=0, le=6)
    pool_max_size: int = Field(default=10, ge=1, le=100)
    log_level: str = Field(default="INFO")
    json_logs: bool = Field(default=True)
    battery_reserve_percent: float = Field(default=20.0, ge=0.0, le=90.0)
    vertical_speed_mps: float = Field(default=3.0, gt=0.0, le=20.0)
    climb_efficiency: float = Field(default=0.6, gt=0.0, le=1.0)
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_s: float = Field(default=60.0, gt=0.0)
    metrics_enabled: bool = Field(default=True)
    checkpoint_retention_days: float = Field(default=30.0, ge=0.0)

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def rate_limit_enabled(self) -> bool:
        """Return whether per-client rate limiting is active."""
        return self.rate_limit_requests > 0

    @property
    def uses_postgres(self) -> bool:
        """Return whether the configured database is PostgreSQL."""
        return self.database_url.startswith("postgresql")

    @property
    def auth_enabled(self) -> bool:
        """Return whether endpoint API-key authentication is enforced."""
        return bool(self.api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

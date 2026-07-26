"""Application configuration.

All runtime configuration is declared here with explicit types and defaults
(Principle 8). Nothing reads ``os.environ`` directly elsewhere in the code.
"""

from functools import lru_cache
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL: Final[str] = "sqlite+aiosqlite:///./suas_local.db"
DEFAULT_WEATHER_URL: Final[str] = "https://api.open-meteo.com/v1/forecast"


class Settings(BaseSettings):
    """Strongly typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SUAS_",
        extra="ignore",
    )

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    api_key: str = Field(default="")
    cors_origins: str = Field(default="http://localhost:3000")
    weather_base_url: str = Field(default=DEFAULT_WEATHER_URL)
    weather_timeout_s: float = Field(default=10.0, gt=0.0)
    weather_retry_attempts: int = Field(default=3, ge=1, le=6)
    llm_timeout_s: float = Field(default=30.0, gt=0.0)
    llm_max_retries: int = Field(default=2, ge=0, le=6)
    pool_max_size: int = Field(default=10, ge=1, le=100)
    log_level: str = Field(default="INFO")

    @property
    def cors_origin_list(self) -> list[str]:
        """Return CORS origins as a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

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

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

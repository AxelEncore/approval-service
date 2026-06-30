"""Application configuration loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    The single most important value is ``database_url``. It defaults to a local
    SQLite file so the service (and its test-suite) can run with zero external
    dependencies, and is overridden to a PostgreSQL DSN in docker-compose.
    """

    app_name: str = "approval-service"
    environment: str = "local"

    # SQLAlchemy URL. PostgreSQL example:
    #   postgresql+psycopg2://approval:approval@db:5432/approval
    database_url: str = "sqlite:///./approval_service.db"

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

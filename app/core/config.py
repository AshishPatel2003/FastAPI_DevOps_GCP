"""
Core application settings.

All configuration is loaded from environment variables (or .env in local dev).
Pydantic Settings validates types and provides defaults.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "FastAPI DevOps GCP"
    APP_VERSION: str = "1.0.0"
    APP_ENV: Literal["development", "staging", "production", "testing"] = "development"
    DEBUG: bool = False

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        """Allow comma-separated string or list."""
        if isinstance(v, str):
            # Split by comma and remove empty entries
            origins = [origin.strip() for origin in v.split(",") if origin.strip()]

            print(f"\nParsed origins: {origins}\n")
            # Remove duplicate origins while preserving order
            seen = set()
            unique_origins = []
            for origin in origins:
                if origin not in seen:
                    unique_origins.append(origin)
                    seen.add(origin)
            return unique_origins
        return v

    # ------------------------------------------------------------------
    # Security / JWT
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = "change-this-secret-key-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ------------------------------------------------------------------
    # Database (PostgreSQL via asyncpg)
    # ------------------------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://fastapi_user:password@localhost:5432/fastapi_db"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # Cloud SQL instance connection name (required on Cloud Run)
    # Format: project-id:region:instance-name
    CLOUD_SQL_INSTANCE: str = ""

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_MAX_CONNECTIONS: int = 10

    # ------------------------------------------------------------------
    # GCP Storage
    # ------------------------------------------------------------------
    GCS_PUBLIC_BUCKET: str = "my-project-public-dev"
    GCS_PRIVATE_BUCKET: str = "my-project-private-dev"
    GCS_SIGNED_URL_EXPIRATION_MINUTES: int = 60

    # ------------------------------------------------------------------
    # GCP General
    # ------------------------------------------------------------------
    GCP_PROJECT_ID: str = ""
    GCP_REGION: str = "asia-south1"
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # ------------------------------------------------------------------
    # GCP Cloud Logging
    # ------------------------------------------------------------------
    ENABLE_GCP_LOGGING: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV in ("development", "testing")

    @property
    def docs_url(self) -> str | None:
        """Only expose interactive docs in non-production environments."""
        return None if self.is_production else "/docs"

    @property
    def redoc_url(self) -> str | None:
        return None if self.is_production else "/redoc"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Enforce strong secrets in production."""
        if self.is_production:
            if self.JWT_SECRET_KEY == "change-this-secret-key-in-production-min-32-chars":
                raise ValueError("JWT_SECRET_KEY must be set to a strong secret in production")
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings (singleton pattern)."""
    return Settings()


# Convenience alias for import throughout the app
settings = get_settings()

"""
Application configuration using Pydantic settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # Database
    DATABASE_URL: str
    POSTGRES_USER: str = "cradler"
    POSTGRES_PASSWORD: str = "cradler_dev_password"
    POSTGRES_DB: str = "cradler"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO / S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_EXTERNAL_ENDPOINT: str = "localhost:9000"  # External endpoint for presigned URLs (accessible from browser)
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "cradler-scraped-data"
    MINIO_SECURE: bool = False

    # Temporal
    TEMPORAL_HOST: str = "localhost:7233"

    # Context7 MCP Server
    CONTEXT7_HOST: str = "localhost:3001"

    # OpenRouter API
    OPENROUTER_API_KEY: str

    # LLM models (OpenRouter model IDs) — override per environment for benchmarking
    PRIMARY_AGENT_MODEL: str = "deepseek/deepseek-v3.2-exp"
    SECONDARY_AGENT_MODEL: str = "deepseek/deepseek-v3.1-terminus"

    # JWT
    JWT_SECRET_KEY: str = "default"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Sentry
    SENTRY_DSN: str = ""

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Scraper Limits
    MAX_SCRAPER_EXECUTION_TIME: int = 600
    MAX_CONCURRENT_SCRAPERS: int = 10

    # Email (to be configured)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@cradler.com"


# Global settings instance
settings = Settings()

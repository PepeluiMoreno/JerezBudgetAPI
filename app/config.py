"""
Configuración centralizada de la aplicación.
Usa pydantic-settings para validar y cargar variables de entorno.
"""
from functools import lru_cache
from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Base de datos ────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://jerezbudget:dev@localhost:5432/jerezbudget"

    # Pool de conexiones
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False  # True para ver SQL en dev

    # ── Redis / Celery ───────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO ────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "jerezbudget-sources"
    minio_secure: bool = False

    # ── API ──────────────────────────────────────────────────────
    api_debug: bool = False
    api_secret_key: str = "dev-secret-key-change-in-production"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8015"]

    # ── OpenDataManager (ODM) ────────────────────────────────────
    odmgr_base_url: str = "http://odmgr_app:8000"
    odmgr_webhook_secret: str = "dev-odmgr-secret-change-in-production"

    # ── Scraping ─────────────────────────────────────────────────
    transparencia_base_url: str = "https://transparencia.jerez.es"
    scrape_interval_hours: int = 24
    http_user_agent: str = "JerezBudgetBot/1.0 (civic-tech; intramurosjerez.org)"
    http_timeout: int = 30

    # ── Logging ──────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "console"  # console | json

    # ── Aplicación ───────────────────────────────────────────────
    app_name: str = "JerezBudget API"
    app_version: str = "0.1.0"

    # Años fiscales soportados
    supported_years: list[int] = list(range(2020, 2027))

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL debe ser una URL de PostgreSQL")
        return v


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuración — cacheado para evitar re-lecturas."""
    return Settings()

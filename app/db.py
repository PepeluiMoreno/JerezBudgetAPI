"""
Motor y sesión asíncrona de SQLAlchemy 2.0.
Provee get_db() como dependencia de FastAPI y get_session() como context manager.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

settings = get_settings()

# ── Motor ───────────────────────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,       # detecta conexiones muertas
    echo=settings.db_echo,
)

# ── Session factory ─────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # importante para async: evita lazy-load tras commit
    autoflush=False,
)


# ── Dependencia FastAPI ──────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Inyección de dependencia para endpoints FastAPI y resolvers GraphQL.

    Uso:
        @strawberry.field
        async def fiscal_years(self, info: strawberry.types.Info) -> list[FiscalYearType]:
            db: AsyncSession = info.context["db"]
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Context manager para tareas Celery ──────────────────────────────────────
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager para uso fuera de FastAPI (ETL, tasks Celery, scripts).

    Uso:
        async with get_session() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

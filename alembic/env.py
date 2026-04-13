"""
Alembic env.py adaptado para SQLAlchemy async con asyncpg.
Detecta DATABASE_URL del entorno para evitar hardcoding.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Importar todos los modelos para que Alembic los detecte ─────────────────
from models import Base   # noqa: F401 — importa Base + todos los modelos

config = context.config

# DATABASE_URL desde variable de entorno (prioridad sobre alembic.ini)
database_url = os.environ.get("DATABASE_URL", "")
if database_url:
    # Online (async): usar asyncpg directamente
    async_url = database_url if database_url.startswith("postgresql+asyncpg://") \
        else database_url.replace("postgresql://", "postgresql+asyncpg://")
    # Offline (autogenerate SQL sin conexión): psycopg2 — solo afecta a run_migrations_offline
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", async_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera SQL sin conexión activa."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Migraciones en modo online con motor async."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

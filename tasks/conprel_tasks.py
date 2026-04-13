"""
Tareas Celery para el pipeline ETL de la Capa 2 (CONPREL + INE).

Pipeline encadenado:
  seed_ine_population    → carga padrón histórico en municipal_population
  ingest_conprel_year    → descarga MDB + parsea + carga en BD
  rebuild_peer_groups    → recalcula grupos de comparación
  refresh_comparison_view → refresca vista materializada

Tarea de carga masiva:
  load_historical_conprel → encola ingest_conprel_year para 2010-2024
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import structlog

from tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run(coro):
    """Ejecuta una corrutina desde un contexto síncrono (worker Celery)."""
    return asyncio.run(coro)


# ── Task 1: Poblar padrón INE ─────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.conprel_tasks.seed_ine_population",
    max_retries=2,
    queue="etl",
    time_limit=1800,  # 30 min — hay ~8k municipios × ~14 años
)
def seed_ine_population(self, ine_codes: Optional[list[str]] = None, batch_size: int = 50):
    """
    Carga la serie histórica de población del INE para todos los municipios
    (o una lista específica si se proporciona).

    Estrategia por lotes para no saturar la API del INE.
    """
    from app.db import AsyncSessionLocal
    from sqlalchemy import select
    from models.national import Municipality
    from etl.ine.population import fetch_population_batch, upsert_population, PADRON_YEARS

    async def _run_seed():
        async with AsyncSessionLocal() as db:
            if ine_codes:
                codes = ine_codes
            else:
                result = await db.execute(
                    select(Municipality.ine_code, Municipality.id)
                    .where(Municipality.is_active == True)
                    .order_by(Municipality.ine_code)
                )
                codes_with_ids = list(result.all())
                codes = [r[0] for r in codes_with_ids]

            logger.info("population_seed_start", total_municipalities=len(codes))

            total_upserted = 0
            for i in range(0, len(codes), batch_size):
                batch = codes[i:i + batch_size]
                logger.debug("population_batch", batch_num=i // batch_size + 1, size=len(batch))

                pop_data = await fetch_population_batch(batch, years=PADRON_YEARS)

                for ine_code, pop_by_year in pop_data.items():
                    if not pop_by_year:
                        continue
                    result = await db.execute(
                        select(Municipality.id).where(Municipality.ine_code == ine_code)
                    )
                    mun_id = result.scalar_one_or_none()
                    if not mun_id:
                        continue
                    n = await upsert_population(db, mun_id, pop_by_year)
                    total_upserted += n

                    # Actualizar population y population_year en municipalities
                    latest_year = max(pop_by_year.keys())
                    result = await db.execute(
                        select(Municipality).where(Municipality.id == mun_id)
                    )
                    mun = result.scalar_one_or_none()
                    if mun:
                        mun.population      = pop_by_year[latest_year]
                        mun.population_year = latest_year

                await db.commit()
                logger.info("population_batch_done", progress=f"{i + len(batch)}/{len(codes)}")

            return total_upserted

    try:
        total = _run(_run_seed())
        logger.info("population_seed_complete", records=total)
        # Tras cargar población, reconstruir peer groups
        rebuild_peer_groups.apply_async(queue="etl", countdown=5)
        return {"status": "ok", "records": total}
    except Exception as exc:
        logger.error("population_seed_failed", error=str(exc))
        raise self.retry(exc=exc)


# ── Task 2: Ingestión de un año CONPREL ──────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.conprel_tasks.ingest_conprel_year",
    max_retries=2,
    default_retry_delay=300,
    queue="etl",
    time_limit=3600,  # 1h — los MDB históricos pueden ser lentos
)
def ingest_conprel_year(self, year: int, mdb_local_path: Optional[str] = None):
    """
    Pipeline completo para un año CONPREL:
    1. Descargar MDB (o usar ruta local si se proporciona)
    2. Parsear todas las tablas con mdbtools
    3. Cargar en BD con cálculo de per-cápita y tasas
    4. Encadenar refresh de vista materializada

    Args:
        year: Año fiscal (ej: 2023)
        mdb_local_path: Ruta local al .mdb si ya está descargado
    """
    from pathlib import Path
    from app.db import AsyncSessionLocal
    from etl.conprel.parser import parse_conprel_mdb
    from etl.conprel.loader import load_conprel_year, refresh_comparison_view

    async def _pipeline():
        # 1. Obtener el MDB
        if mdb_local_path:
            mdb_path = Path(mdb_local_path)
            logger.info("using_local_mdb", year=year, path=str(mdb_path))
        else:
            from etl.conprel.downloader import download_conprel_mdb
            mdb_path = await download_conprel_mdb(year)

        try:
            # 2. Parsear
            logger.info("parsing_conprel", year=year, mdb=str(mdb_path))
            records, stats = parse_conprel_mdb(mdb_path, year)

            if not records:
                raise ValueError(
                    f"El parser no extrajo ningún registro del MDB {year}. "
                    f"Tablas encontradas: {stats.tables_found}. "
                    f"Tablas no encontradas: {stats.tables_missing}"
                )

            logger.info(
                "parse_complete",
                year=year,
                records=stats.records_extracted,
                municipalities=len(stats.municipalities_found),
            )

            # 3. Cargar en BD
            async with AsyncSessionLocal() as db:
                result = await load_conprel_year(db, records, year)
                await db.commit()

            logger.info(
                "load_complete",
                year=year,
                municipalities=result.municipalities_loaded,
                chapters=result.chapters_loaded,
                missing=len(result.municipalities_missing),
            )

            if result.municipalities_missing:
                logger.warning(
                    "municipalities_not_in_catalog",
                    year=year,
                    count=len(result.municipalities_missing),
                    sample=result.municipalities_missing[:5],
                )

            # 4. Refrescar vista materializada
            async with AsyncSessionLocal() as db:
                await refresh_comparison_view(db)
                await db.commit()

            return {
                "year": year,
                "records": stats.records_extracted,
                "municipalities": result.municipalities_loaded,
                "chapters": result.chapters_loaded,
            }

        finally:
            # Limpiar temporal (solo si lo descargamos nosotros)
            if not mdb_local_path:
                mdb_path.unlink(missing_ok=True)

    try:
        result = _run(_pipeline())
        logger.info("conprel_year_ingested", **result)
        return result
    except Exception as exc:
        logger.error("conprel_ingest_failed", year=year, error=str(exc))
        raise self.retry(exc=exc)


# ── Task 3: Reconstruir peer groups ──────────────────────────────────────────

@celery_app.task(
    name="tasks.conprel_tasks.rebuild_peer_groups",
    queue="etl",
)
def rebuild_peer_groups():
    """
    Recalcula los miembros de todos los peer groups dinámicos.
    Se encadena automáticamente tras seed_ine_population.
    """
    from app.db import AsyncSessionLocal
    from services.peer_groups import rebuild_dynamic_peer_groups, ensure_jerez_in_all_groups

    async def _rebuild():
        async with AsyncSessionLocal() as db:
            stats = await rebuild_dynamic_peer_groups(db)
            await ensure_jerez_in_all_groups(db)
            await db.commit()
            return stats

    stats = _run(_rebuild())
    logger.info("peer_groups_rebuilt", stats=stats)
    return stats


# ── Task 4: Carga histórica masiva ───────────────────────────────────────────

@celery_app.task(
    name="tasks.conprel_tasks.load_historical_conprel",
    queue="etl",
    time_limit=60,
)
def load_historical_conprel(
    years: Optional[list[int]] = None,
    countdown_between: int = 60,
):
    """
    Encola la ingestión del histórico CONPREL completo.
    Cada año se procesa de forma independiente con un delay entre ellos
    para no saturar el servidor del Ministerio de Hacienda.

    Uso desde CLI:
        celery -A tasks.celery_app call tasks.conprel_tasks.load_historical_conprel

    Uso con años específicos:
        celery -A tasks.celery_app call tasks.conprel_tasks.load_historical_conprel
          --kwargs '{"years": [2022, 2023, 2024]}'
    """
    from etl.conprel.schema import CONPREL_AVAILABLE_YEARS

    target_years = years or CONPREL_AVAILABLE_YEARS
    logger.info("historical_load_start", years=target_years)

    for i, year in enumerate(sorted(target_years)):
        delay = i * countdown_between  # escalonado: 0s, 60s, 120s...
        ingest_conprel_year.apply_async(
            kwargs={"year": year},
            countdown=delay,
            queue="etl",
        )
        logger.info("year_enqueued", year=year, starts_in_seconds=delay)

    return {"years_enqueued": target_years, "total": len(target_years)}


# ── Scheduler anual ───────────────────────────────────────────────────────────
# Añadir al beat_schedule en celery_app.py:
#
# "conprel-annual-liquidation": {
#     "task": "tasks.conprel_tasks.ingest_conprel_year",
#     "schedule": crontab(month_of_year=1, day_of_month=15, hour=7),
#     "kwargs": {"year": datetime.now().year - 1},
# }

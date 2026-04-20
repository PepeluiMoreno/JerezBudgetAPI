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
    # Sin time_limit: duración depende de la API del INE (~1 s × 8 k municipios)
)
def seed_ine_population(self, ine_codes: Optional[list[str]] = None, batch_size: int = 50):
    """
    Carga la serie histórica de población del INE.
    Reanudable: omite municipios que ya tienen datos en municipal_population.
    """
    from app.db import AsyncSessionLocal
    from sqlalchemy import select
    from models.national import Municipality
    from models.national import MunicipalPopulation
    from etl.ine.population import upsert_population, PADRON_YEARS

    async def _run_seed():
        from app.db import engine
        from etl.ine.population import fetch_all_population_bulk
        await engine.dispose()   # libera conexiones del loop anterior

        async with AsyncSessionLocal() as db:
            # Todos los municipios activos ordenados
            result = await db.execute(
                select(Municipality.ine_code)
                .where(Municipality.is_active == True)
                .order_by(Municipality.ine_code)
            )
            all_codes = [r[0] for r in result.all()] if not ine_codes else ine_codes

            # Municipios que ya tienen al menos un registro → se saltan
            done_result = await db.execute(
                select(Municipality.ine_code)
                .join(MunicipalPopulation,
                      MunicipalPopulation.municipality_id == Municipality.id)
                .distinct()
            )
            already_done = {r[0] for r in done_result.all()}
            pending = [c for c in all_codes if c not in already_done]

        logger.info(
            "population_seed_start",
            total=len(all_codes),
            already_done=len(already_done),
            pending=len(pending),
        )

        if not pending:
            logger.info("population_seed_already_complete")
            return 0

        # ── Descarga masiva ÚNICA — 1 llamada en lugar de ~8000 ──────────────
        bulk_data = await fetch_all_population_bulk(years=PADRON_YEARS)
        logger.info(
            "population_bulk_ready",
            municipalities_in_api=len(bulk_data),
            pending_in_db=len(pending),
        )

        total_upserted = 0
        async with AsyncSessionLocal() as db:
            for i in range(0, len(pending), batch_size):
                batch = pending[i:i + batch_size]

                for code in batch:
                    pop_by_year = bulk_data.get(code, {})
                    if not pop_by_year:
                        logger.debug("population_not_in_api", ine_code=code)
                        continue
                    res = await db.execute(
                        select(Municipality).where(Municipality.ine_code == code)
                    )
                    mun = res.scalar_one_or_none()
                    if not mun:
                        continue
                    n = await upsert_population(db, mun.id, pop_by_year)
                    total_upserted += n
                    latest_year = max(pop_by_year.keys())
                    mun.population      = pop_by_year[latest_year]
                    mun.population_year = latest_year

                await db.commit()
                done_so_far = len(already_done) + i + len(batch)
                logger.info(
                    "population_batch_done",
                    progress=f"{done_so_far}/{len(all_codes)}",
                    pct=round(done_so_far / len(all_codes) * 100, 1),
                )

        return total_upserted

    try:
        total = _run(_run_seed())
        logger.info("population_seed_complete", records=total)
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
        from app.db import engine
        await engine.dispose()   # libera conexiones del loop anterior
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
    from services.peer_groups import rebuild_dynamic_peer_groups, ensure_city_in_all_groups

    async def _rebuild():
        from app.db import engine
        await engine.dispose()   # libera conexiones del loop anterior
        async with AsyncSessionLocal() as db:
            stats = await rebuild_dynamic_peer_groups(db)
            await ensure_city_in_all_groups(db)
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

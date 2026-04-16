"""
Tareas Celery para el scraping de la Cuenta General desde rendiciondecuentas.es.

Extrae KPIs de sostenibilidad (indicadores financiero-patrimoniales oficiales,
remanente de tesorería, cuenta de resultado económico-patrimonial, balance)
directamente del Portal del Ciudadano del Tribunal de Cuentas.

Tareas:
  scrape_cuenta_general_year  → extrae y persiste los KPIs de un ejercicio
  load_historical_cg           → encola scrape_cuenta_general_year para 2016-2022
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import structlog

from tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)

# ── Entidades configuradas (NIF, id_entidad, etiqueta) ───────────────────────
# Añadir aquí otros municipios del grupo de comparación si se desea.
_ENTITIES: list[dict] = [
    {
        "nif":         "P1102000E",
        "id_entidad":  1779,
        "label":       "Jerez de la Frontera",
    },
]

# Años disponibles en rendiciondecuentas.es para municipios NOR modelo 3
_CG_AVAILABLE_YEARS: list[int] = list(range(2016, 2023))  # 2016-2022


# ── Task: scrape un ejercicio ────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.cuenta_general_tasks.scrape_cuenta_general_year",
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=180,
    time_limit=240,
    queue="etl",
)
def scrape_cuenta_general_year(
    self,
    nif: str,
    id_entidad: int,
    ejercicio: int,
    label: str = "",
) -> dict:
    """
    Descarga y persiste los KPIs de la Cuenta General de una entidad y ejercicio.

    Devuelve: {"kpis_upserted": int, "ejercicio": int, "nif": str}
    """
    from app.db import AsyncSessionLocal, engine
    from models.socioeconomic import CuentaGeneralKpi
    from services.cuentas_scraper import scrape_cg_kpis
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import asyncio

    logger.info(
        "cg_scrape_task_start",
        nif=nif,
        id_entidad=id_entidad,
        ejercicio=ejercicio,
        label=label,
    )

    # Scraping is synchronous (requests library, no event loop needed)
    try:
        kpis = scrape_cg_kpis(
            nif=nif,
            id_entidad=id_entidad,
            ejercicio=ejercicio,
        )
    except ValueError as exc:
        # Ejercicio not available (403) — not retryable
        logger.warning("cg_scrape_unavailable", ejercicio=ejercicio, error=str(exc))
        return {"kpis_upserted": 0, "ejercicio": ejercicio, "nif": nif, "skipped": True}
    except Exception as exc:
        logger.error("cg_scrape_failed", ejercicio=ejercicio, error=str(exc))
        raise self.retry(exc=exc)

    if not kpis:
        logger.warning("cg_scrape_empty", ejercicio=ejercicio, nif=nif)
        return {"kpis_upserted": 0, "ejercicio": ejercicio, "nif": nif}

    # Persist via upsert
    async def _upsert():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            stmt = pg_insert(CuentaGeneralKpi).values(kpis)
            stmt = stmt.on_conflict_do_update(
                index_elements=["nif_entidad", "ejercicio", "kpi"],
                set_={
                    "valor":            stmt.excluded.valor,
                    "unidad":           stmt.excluded.unidad,
                    "fuente_cuenta":    stmt.excluded.fuente_cuenta,
                    "odmgr_dataset_id": stmt.excluded.odmgr_dataset_id,
                },
            )
            await db.execute(stmt)
            await db.commit()
        return len(kpis)

    count = asyncio.run(_upsert())
    logger.info("cg_scrape_task_done", kpis_upserted=count, ejercicio=ejercicio, nif=nif)
    return {"kpis_upserted": count, "ejercicio": ejercicio, "nif": nif}


# ── Task: carga histórica masiva ─────────────────────────────────────────────

@celery_app.task(
    name="tasks.cuenta_general_tasks.load_historical_cg",
    queue="etl",
    time_limit=120,
)
def load_historical_cg(
    years: Optional[list[int]] = None,
    countdown_between: int = 90,
):
    """
    Encola scrape_cuenta_general_year para todos los ejercicios y entidades.

    Escalonado para no saturar el portal del Tribunal de Cuentas.

    Uso desde CLI:
        docker exec jerezbudget_worker celery -A tasks.celery_app call \\
            tasks.cuenta_general_tasks.load_historical_cg

    Con años específicos:
        docker exec jerezbudget_worker celery -A tasks.celery_app call \\
            tasks.cuenta_general_tasks.load_historical_cg \\
            --kwargs '{"years": [2020, 2021, 2022]}'
    """
    target_years = years or _CG_AVAILABLE_YEARS
    logger.info("cg_historical_start", years=target_years, entities=len(_ENTITIES))

    i = 0
    for entity in _ENTITIES:
        for yr in sorted(target_years):
            delay = i * countdown_between
            scrape_cuenta_general_year.apply_async(
                kwargs={
                    "nif":        entity["nif"],
                    "id_entidad": entity["id_entidad"],
                    "ejercicio":  yr,
                    "label":      entity["label"],
                },
                countdown=delay,
                queue="etl",
            )
            logger.info(
                "cg_year_enqueued",
                label=entity["label"],
                year=yr,
                starts_in_seconds=delay,
            )
            i += 1

    total = len(_ENTITIES) * len(target_years)
    return {"years_enqueued": target_years, "entities": len(_ENTITIES), "total_tasks": total}

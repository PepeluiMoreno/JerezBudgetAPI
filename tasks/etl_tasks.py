"""
Tareas Celery del pipeline ETL.

Flujo principal (encadenado):
  discover_and_ingest → [ingest_file × N] → compute_metrics

Cada tarea es idempotente: si el fichero ya está en MinIO con el mismo
SHA256, o el snapshot ya existe en BD, no hace trabajo duplicado.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run(coro):
    """Ejecuta una corrutina desde un contexto síncrono (worker Celery)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Task 1: Discovery ────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.etl_tasks.discover_and_ingest",
    max_retries=3,
    default_retry_delay=120,
    queue="etl",
)
def discover_and_ingest(self, years: Optional[list[int]] = None):
    """
    Descubre ficheros nuevos en transparencia.jerez.es y encola su ingestión.

    Args:
        years: Lista de años a explorar. None = todos los años configurados.
    """
    from etl.scraper import TransparenciaScraper, FileType
    from app.db import AsyncSessionLocal
    from models.budget import BudgetSnapshot
    from sqlalchemy import select

    logger.info("discovery_start", years=years or "all")

    async def _discover():
        async with TransparenciaScraper() as scraper:
            files = await scraper.discover_all(years=years)
        return files

    try:
        discovered = _run(_discover())
    except Exception as exc:
        logger.error("discovery_failed", error=str(exc))
        raise self.retry(exc=exc)

    # Filtrar solo XLSX de ejecución (los PDFs de modificaciones los gestiona el admin)
    xlsx_files = [
        f for f in discovered
        if f.file_type in (FileType.EXECUTION_EXPENSES, FileType.EXECUTION_REVENUES)
    ]

    logger.info(
        "discovery_done",
        total=len(discovered),
        xlsx=len(xlsx_files),
    )

    # Encolar ingestión de cada XLSX
    for file_info in xlsx_files:
        ingest_file.apply_async(
            kwargs={"file_info_dict": _file_to_dict(file_info)},
            queue="etl",
        )

    return {
        "discovered": len(discovered),
        "xlsx_enqueued": len(xlsx_files),
        "years": years,
    }


# ── Task 2: Ingestión de un fichero ─────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.etl_tasks.ingest_file",
    max_retries=3,
    default_retry_delay=60,
    queue="etl",
    time_limit=300,    # 5 minutos máximo por fichero
)
def ingest_file(self, file_info_dict: dict):
    """
    Descarga, parsea y carga en BD un XLSX de ejecución presupuestaria.
    Encadena compute_metrics si la carga es exitosa.
    """
    from etl.scraper import DiscoveredFile, FileType
    from etl.downloader import download_file
    from etl.parsers.xlsx_execution import parse_execution_xlsx
    from etl.loader import load_execution_snapshot
    from app.db import AsyncSessionLocal

    file_info = _dict_to_file(file_info_dict)

    logger.info(
        "ingest_start",
        filename=file_info.filename,
        year=file_info.fiscal_year,
        type=file_info.file_type,
    )

    async def _ingest():
        # 1. Descargar
        download_result = await download_file(file_info)

        if download_result.already_existed:
            # El SHA ya estaba — comprobar si el snapshot también
            # Si ya existe, no hay nada que hacer
            logger.info("file_already_processed", sha256=download_result.sha256[:12])
            return None

        # 2. Parsear
        hint = "expense" if file_info.file_type == FileType.EXECUTION_EXPENSES else "revenue"
        parse_result = parse_execution_xlsx(download_result.local_path, hint_direction=hint)

        if not parse_result.lines:
            logger.warning(
                "parse_empty_result",
                filename=file_info.filename,
                warnings=parse_result.warnings,
            )
            return None

        # 3. Cargar en BD
        async with AsyncSessionLocal() as db:
            stats = await load_execution_snapshot(
                db=db,
                file_info=file_info,
                parse_result=parse_result,
                sha256=download_result.sha256,
                minio_key=download_result.minio_key,
            )
            await db.commit()

        # 4. Limpiar temporal
        try:
            download_result.local_path.unlink(missing_ok=True)
        except Exception:
            pass

        return stats

    try:
        stats = _run(_ingest())
    except Exception as exc:
        logger.error("ingest_failed", filename=file_info.filename, error=str(exc))
        raise self.retry(exc=exc)

    if stats and not stats.already_existed:
        logger.info(
            "ingest_complete",
            year=stats.fiscal_year,
            lines=stats.lines_inserted,
            snapshot_id=stats.snapshot_id,
        )
        # Encadenar cálculo de métricas
        compute_metrics.apply_async(
            kwargs={"fiscal_year": file_info.fiscal_year},
            queue="metrics",
            countdown=5,   # esperar 5s para que el commit se propague
        )

    return {
        "filename": file_info.filename,
        "year": file_info.fiscal_year,
        "lines": stats.lines_inserted if stats else 0,
        "already_existed": stats.already_existed if stats else True,
    }


# ── Task 3: Cálculo de métricas ──────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.etl_tasks.compute_metrics",
    max_retries=2,
    queue="metrics",
)
def compute_metrics(self, fiscal_year: int):
    """
    Calcula y persiste las métricas de rigor para un ejercicio.
    Se ejecuta automáticamente tras cada ingestión exitosa.
    """
    from services.metrics import RigorMetricsService
    from app.db import AsyncSessionLocal

    logger.info("compute_metrics_start", year=fiscal_year)

    async def _compute():
        async with AsyncSessionLocal() as db:
            service = RigorMetricsService(db)
            metrics = await service.compute_and_store(fiscal_year)
            await db.commit()
            return metrics

    try:
        metrics = _run(_compute())
        logger.info(
            "compute_metrics_done",
            year=fiscal_year,
            score=float(metrics.global_rigor_score) if metrics and metrics.global_rigor_score else None,
        )
        return {"fiscal_year": fiscal_year, "success": True}
    except Exception as exc:
        logger.error("compute_metrics_failed", year=fiscal_year, error=str(exc))
        raise self.retry(exc=exc)


# ── Tarea de carga histórica (one-shot) ──────────────────────────────────────

@celery_app.task(
    name="tasks.etl_tasks.load_historical",
    queue="etl",
    time_limit=3600,   # 1 hora para el histórico completo
)
def load_historical(years: Optional[list[int]] = None):
    """
    Carga el histórico completo de ejecuciones.
    Diseñada para ejecutarse una sola vez en el arranque inicial.

    Uso desde CLI:
        celery -A tasks.celery_app call tasks.etl_tasks.load_historical
    """
    target_years = years or [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    logger.info("historical_load_start", years=target_years)

    for year in target_years:
        discover_and_ingest.apply_async(
            kwargs={"years": [year]},
            queue="etl",
        )
        logger.info("historical_year_enqueued", year=year)

    return {"years_enqueued": target_years}


# ── Helpers de serialización ─────────────────────────────────────────────────

def _file_to_dict(file_info) -> dict:
    from datetime import date
    return {
        "url": file_info.url,
        "filename": file_info.filename,
        "file_type": str(file_info.file_type),
        "fiscal_year": file_info.fiscal_year,
        "snapshot_date": file_info.snapshot_date.isoformat() if file_info.snapshot_date else None,
        "mod_ref": file_info.mod_ref,
        "raw_label": file_info.raw_label,
    }


def _dict_to_file(d: dict):
    from datetime import date
    from etl.scraper import DiscoveredFile, FileType
    return DiscoveredFile(
        url=d["url"],
        filename=d["filename"],
        file_type=FileType(d["file_type"]),
        fiscal_year=d["fiscal_year"],
        snapshot_date=date.fromisoformat(d["snapshot_date"]) if d.get("snapshot_date") else None,
        mod_ref=d.get("mod_ref"),
        raw_label=d.get("raw_label", ""),
    )

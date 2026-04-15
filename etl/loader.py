"""
Cargador de datos presupuestarios en PostgreSQL.

Flujo por fichero XLSX:
  1. Obtener o crear FiscalYear
  2. Verificar que no existe ya un snapshot con el mismo SHA256
  3. Insertar BudgetSnapshot
  4. Para cada línea parseada:
     a. Upsert EconomicClassification (por código)
     b. Upsert FunctionalClassification (por código)
     c. Upsert OrganicClassification (por código)
     d. Insert BudgetLine
  5. Retornar stats de carga

Usa INSERT ... ON CONFLICT DO UPDATE para ser idempotente.
Todo en una sola transacción — si falla algo, no queda basura.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from etl.parsers.xlsx_execution import ParseResult, ParsedBudgetLine
from etl.scraper import DiscoveredFile, FileType
from models.budget import (
    BudgetLine,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    FunctionalClassification,
    OrganicClassification,
)

logger = structlog.get_logger(__name__)

# ── Nomenclatura capítulos ───────────────────────────────────────────────────
_CHAPTER_NAMES_EXPENSE = {
    "1": "Personal",
    "2": "Bienes corrientes y servicios",
    "3": "Gastos financieros",
    "4": "Transferencias corrientes",
    "5": "Fondo de contingencia",
    "6": "Inversiones reales",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}
_CHAPTER_NAMES_REVENUE = {
    "1": "Impuestos directos",
    "2": "Impuestos indirectos",
    "3": "Tasas y otros ingresos",
    "4": "Transferencias corrientes",
    "5": "Ingresos patrimoniales",
    "6": "Enajenación de inversiones",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}


@dataclass
class LoadStats:
    fiscal_year: int
    snapshot_date: date
    snapshot_id: int
    lines_inserted: int = 0
    classifications_upserted: int = 0
    already_existed: bool = False      # snapshot con ese SHA ya estaba
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


# ── Helpers clasificaciones ──────────────────────────────────────────────────

def _extract_chapter(code: str) -> str:
    return code[0] if code else ""


def _extract_article(code: str) -> Optional[str]:
    return code[:2] if len(code) >= 2 else None


def _extract_concept(code: str) -> Optional[str]:
    return code[:5] if len(code) >= 5 else None


async def _upsert_economic(
    db: AsyncSession,
    code: str,
    description: str,
    direction: str,
) -> int:
    """Upsert EconomicClassification, retorna id."""
    chapter = _extract_chapter(code)
    names = _CHAPTER_NAMES_EXPENSE if direction == "expense" else _CHAPTER_NAMES_REVENUE
    chapter_desc = names.get(chapter, f"Capítulo {chapter}")

    stmt = pg_insert(EconomicClassification).values(
        code=code,
        chapter=chapter,
        article=_extract_article(code),
        concept=_extract_concept(code),
        description=description or chapter_desc,
        direction=direction,
    ).on_conflict_do_update(
        index_elements=["code"],
        set_={"description": description or chapter_desc},
    ).returning(EconomicClassification.id)

    result = await db.execute(stmt)
    return result.scalar_one()


async def _upsert_functional(
    db: AsyncSession,
    code: str,
    description: str = "",
) -> int:
    """Upsert FunctionalClassification, retorna id."""
    stmt = pg_insert(FunctionalClassification).values(
        code=code,
        area=code[0] if code else None,
        policy=code[:2] if len(code) >= 2 else None,
        program_group=code[:3] if len(code) >= 3 else None,
        program=code[:4] if len(code) >= 4 else None,
        description=description or f"Programa {code}",
    ).on_conflict_do_update(
        index_elements=["code"],
        set_={"description": description or f"Programa {code}"},
    ).returning(FunctionalClassification.id)

    result = await db.execute(stmt)
    return result.scalar_one()


async def _upsert_organic(
    db: AsyncSession,
    code: str,
    description: str = "",
) -> int:
    """Upsert OrganicClassification, retorna id."""
    stmt = pg_insert(OrganicClassification).values(
        code=code,
        section=code[:2] if len(code) >= 2 else None,
        service=code[:4] if len(code) >= 4 else None,
        description=description or f"Sección {code}",
    ).on_conflict_do_update(
        index_elements=["code"],
        set_={"description": description or f"Sección {code}"},
    ).returning(OrganicClassification.id)

    result = await db.execute(stmt)
    return result.scalar_one()


# ── Loader principal ─────────────────────────────────────────────────────────

async def load_execution_snapshot(
    db: AsyncSession,
    file_info: DiscoveredFile,
    parse_result: ParseResult,
    sha256: str,
    minio_key: str,
) -> LoadStats:
    """
    Carga un snapshot de ejecución presupuestaria en la base de datos.
    Idempotente: si ya existe un snapshot con el mismo SHA256, no hace nada.
    """
    fiscal_year = file_info.fiscal_year
    snapshot_date = file_info.snapshot_date or date.today()
    direction = parse_result.direction

    stats = LoadStats(
        fiscal_year=fiscal_year,
        snapshot_date=snapshot_date,
        snapshot_id=0,
    )

    if not parse_result.lines:
        stats.warnings.append("El parse no produjo ninguna línea — no se carga nada")
        return stats

    # ── 1. FiscalYear ────────────────────────────────────────────────────────
    fy_result = await db.execute(
        select(FiscalYear).where(FiscalYear.year == fiscal_year)
    )
    fy = fy_result.scalar_one_or_none()
    if not fy:
        fy = FiscalYear(
            year=fiscal_year,
            status="draft",
            is_extension=(fiscal_year == 2026),
            extended_from_year=2025 if fiscal_year == 2026 else None,
        )
        db.add(fy)
        await db.flush()
        logger.info("fiscal_year_created", year=fiscal_year)

    # ── 2. Deduplicación por SHA256 ──────────────────────────────────────────
    existing = await db.execute(
        select(BudgetSnapshot).where(BudgetSnapshot.source_sha256 == sha256)
    )
    if existing.scalar_one_or_none():
        logger.info("snapshot_already_exists", sha256=sha256[:12], year=fiscal_year)
        stats.already_existed = True
        return stats

    # ── 3. BudgetSnapshot ────────────────────────────────────────────────────
    if file_info.file_type == FileType.EXECUTION_EXPENSES:
        phase = "executed_expense"
    elif file_info.file_type == FileType.EXECUTION_REVENUES:
        phase = "executed_revenue"
    else:
        phase = "executed"

    snapshot = BudgetSnapshot(
        fiscal_year_id=fy.id,
        snapshot_date=snapshot_date,
        phase=phase,
        source_url=file_info.url,
        source_sha256=sha256,
        minio_path=minio_key,
    )
    db.add(snapshot)
    await db.flush()
    stats.snapshot_id = snapshot.id

    logger.info(
        "snapshot_created",
        snapshot_id=snapshot.id,
        year=fiscal_year,
        date=snapshot_date,
        lines=len(parse_result.lines),
    )

    # ── 4. Líneas presupuestarias ────────────────────────────────────────────
    # Cache de clasificaciones para evitar N queries por línea
    economic_cache: dict[str, int] = {}
    functional_cache: dict[str, int] = {}
    organic_cache: dict[str, int] = {}

    batch: list[dict] = []

    for line in parse_result.lines:
        # EconomicClassification
        eco_key = f"{line.economic_code}:{direction}"
        if eco_key not in economic_cache:
            eco_id = await _upsert_economic(db, line.economic_code, line.description, direction)
            economic_cache[eco_key] = eco_id
            stats.classifications_upserted += 1
        eco_id = economic_cache[eco_key]

        # FunctionalClassification (solo si tiene código)
        func_id = None
        if line.functional_code:
            if line.functional_code not in functional_cache:
                func_id = await _upsert_functional(db, line.functional_code)
                functional_cache[line.functional_code] = func_id
                stats.classifications_upserted += 1
            func_id = functional_cache[line.functional_code]

        # OrganicClassification
        org_id = None
        if line.organic_code:
            if line.organic_code not in organic_cache:
                org_id = await _upsert_organic(db, line.organic_code)
                organic_cache[line.organic_code] = org_id
                stats.classifications_upserted += 1
            org_id = organic_cache[line.organic_code]

        batch.append({
            "snapshot_id": snapshot.id,
            "organic_id": org_id,
            "functional_id": func_id,
            "economic_id": eco_id,
            "description": line.description,
            # Gastos
            "initial_credits": line.initial_credits,
            "modifications": line.modifications,
            "final_credits": line.final_credits,
            "commitments": line.commitments,
            "recognized_obligations": line.recognized_obligations,
            "payments_made": line.payments_made,
            "pending_payment": line.pending_payment,
            # Ingresos
            "initial_forecast": line.initial_forecast,
            "final_forecast": line.final_forecast,
            "recognized_rights": line.recognized_rights,
            "net_collection": line.net_collection,
            "pending_collection": line.pending_collection,
        })

    # Insert en lotes de 500
    BATCH_SIZE = 500
    for i in range(0, len(batch), BATCH_SIZE):
        chunk = batch[i:i + BATCH_SIZE]
        await db.execute(pg_insert(BudgetLine), chunk)
        stats.lines_inserted += len(chunk)
        logger.debug("batch_inserted", batch_num=i // BATCH_SIZE + 1, count=len(chunk))

    stats.warnings.extend(parse_result.warnings)

    logger.info(
        "load_complete",
        snapshot_id=snapshot.id,
        year=fiscal_year,
        lines=stats.lines_inserted,
        classifications=stats.classifications_upserted,
    )
    return stats

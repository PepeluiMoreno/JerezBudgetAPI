"""
Cargador de datos CONPREL en PostgreSQL.

Flujo por año:
  1. Agrupar ConprelRecords por (entity_code, data_type, direction)
  2. Para cada municipio:
     a. Buscar municipality_id por ine_code
     b. Upsert MunicipalBudget (cabecera con totales)
     c. Upsert MunicipalBudgetChapter (detalle capítulos)
     d. Upsert MunicipalBudgetProgram (áreas funcionales)
  3. Calcular per-cápita usando MunicipalPopulation del año
  4. Calcular tasas de ejecución y modificación
  5. Actualizar totales en MunicipalBudget
  6. Refrescar vista materializada mv_comparison_jerez

Es completamente idempotente: ON CONFLICT DO UPDATE en todos los upserts.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from etl.conprel.schema import (
    AREA_NAMES,
    CHAPTER_NAMES_EXPENSE,
    CHAPTER_NAMES_REVENUE,
    ConprelRecord,
    DataType,
    Direction,
)
from models.national import (
    Municipality,
    MunicipalBudget,
    MunicipalBudgetChapter,
    MunicipalBudgetProgram,
    MunicipalPopulation,
)

logger = structlog.get_logger(__name__)


@dataclass
class LoadResult:
    fiscal_year: int
    municipalities_loaded: int = 0
    chapters_loaded: int = 0
    programs_loaded: int = 0
    municipalities_missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _d(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _rate(numerator, denominator) -> Optional[Decimal]:
    n, d = _d(numerator), _d(denominator)
    if d <= 0:
        return None
    return (n / d).quantize(Decimal("0.0001"))


async def _get_population(
    db: AsyncSession,
    municipality_id: int,
    year: int,
) -> Optional[int]:
    """Devuelve la población del municipio para el año dado o el más cercano."""
    result = await db.execute(
        select(MunicipalPopulation.population)
        .where(MunicipalPopulation.municipality_id == municipality_id)
        .where(MunicipalPopulation.year == year)
    )
    pop = result.scalar_one_or_none()
    if pop:
        return pop

    # Si no hay dato exacto, buscar el más cercano (±3 años)
    result = await db.execute(
        select(MunicipalPopulation.population, MunicipalPopulation.year)
        .where(MunicipalPopulation.municipality_id == municipality_id)
        .where(MunicipalPopulation.year.between(year - 3, year + 3))
        .order_by(text(f"ABS(year - {year})"))
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


def _per_capita(amount: Optional[Decimal], population: Optional[int]) -> Optional[Decimal]:
    if amount is None or not population:
        return None
    return (amount / Decimal(population)).quantize(Decimal("0.01"))


async def load_conprel_year(
    db: AsyncSession,
    records: list[ConprelRecord],
    fiscal_year: int,
) -> LoadResult:
    """
    Carga todos los registros CONPREL de un año en la base de datos.
    Idempotente — puede ejecutarse múltiples veces sin duplicar datos.
    """
    result = LoadResult(fiscal_year=fiscal_year)

    if not records:
        logger.warning("no_records_to_load", year=fiscal_year)
        return result

    # ── Agrupar registros por municipio + data_type ───────────────────────────
    # Estructura: {(ine_code, data_type) → {(chapter, direction) → record}}
    by_mun: dict[tuple[str, str], dict[tuple[str, str], ConprelRecord]] = defaultdict(dict)
    programs: dict[tuple[str, str], dict[str, ConprelRecord]] = defaultdict(dict)

    for rec in records:
        key = (rec.entity_code, rec.data_type.value)
        ch_key = (rec.chapter, rec.direction.value)

        if rec.table_name and "FUNC" in rec.table_name.upper():
            # Es un registro de clasificación funcional (área)
            programs[key][rec.chapter] = rec
        else:
            by_mun[key][ch_key] = rec

    # ── Cargar catálogo de municipios en memoria (para lookups rápidos) ───────
    mun_result = await db.execute(
        select(Municipality.ine_code, Municipality.id, Municipality.population)
    )
    mun_lookup: dict[str, tuple[int, Optional[int]]] = {
        row[0]: (row[1], row[2]) for row in mun_result.all()
    }

    logger.info(
        "loading_conprel",
        year=fiscal_year,
        municipality_groups=len(by_mun),
        known_municipalities=len(mun_lookup),
    )

    # ── Procesar cada municipio ───────────────────────────────────────────────
    processed_budgets: dict[tuple[str, str], int] = {}  # (ine_code, data_type) → budget_id

    for (ine_code, data_type_str), chapters in by_mun.items():
        if ine_code not in mun_lookup:
            result.municipalities_missing.append(ine_code)
            continue

        mun_id, mun_pop = mun_lookup[ine_code]
        population = await _get_population(db, mun_id, fiscal_year) or mun_pop

        # ── Calcular totales del presupuesto ──────────────────────────────────
        expense_chapters = {
            ch: rec for (ch, dir_), rec in chapters.items()
            if dir_ == Direction.EXPENSE.value
        }
        revenue_chapters = {
            ch: rec for (ch, dir_), rec in chapters.items()
            if dir_ == Direction.REVENUE.value
        }

        total_exp_initial  = sum((_d(r.initial_amount)  for r in expense_chapters.values()), Decimal("0")) or None
        total_exp_final    = sum((_d(r.final_amount)    for r in expense_chapters.values()), Decimal("0")) or None
        total_exp_executed = sum((_d(r.executed_amount) for r in expense_chapters.values()), Decimal("0")) or None
        total_rev_initial  = sum((_d(r.initial_amount)  for r in revenue_chapters.values()), Decimal("0")) or None
        total_rev_executed = sum((_d(r.executed_amount) for r in revenue_chapters.values()), Decimal("0")) or None

        exp_exec_rate = _rate(total_exp_executed, total_exp_final or total_exp_initial)
        rev_exec_rate = _rate(total_rev_executed, total_rev_initial)
        mod_rate      = _rate(
            _d(total_exp_final) - _d(total_exp_initial),
            total_exp_initial
        ) if total_exp_initial else None

        exp_per_cap = _per_capita(total_exp_executed, population)
        rev_per_cap = _per_capita(total_rev_executed, population)

        # ── Upsert MunicipalBudget ────────────────────────────────────────────
        budget_stmt = pg_insert(MunicipalBudget).values(
            municipality_id=mun_id,
            fiscal_year=fiscal_year,
            data_type=data_type_str,
            conprel_year=fiscal_year,
            total_expense_initial=total_exp_initial,
            total_expense_final=total_exp_final,
            total_expense_executed=total_exp_executed,
            total_revenue_initial=total_rev_initial,
            total_revenue_executed=total_rev_executed,
            expense_executed_per_capita=exp_per_cap,
            revenue_executed_per_capita=rev_per_cap,
            expense_execution_rate=exp_exec_rate,
            revenue_execution_rate=rev_exec_rate,
            modification_rate=mod_rate,
        ).on_conflict_do_update(
            constraint="uq_mun_budget_year_type",
            set_={
                "total_expense_initial":        total_exp_initial,
                "total_expense_final":          total_exp_final,
                "total_expense_executed":       total_exp_executed,
                "total_revenue_initial":        total_rev_initial,
                "total_revenue_executed":       total_rev_executed,
                "expense_executed_per_capita":  exp_per_cap,
                "revenue_executed_per_capita":  rev_per_cap,
                "expense_execution_rate":       exp_exec_rate,
                "revenue_execution_rate":       rev_exec_rate,
                "modification_rate":            mod_rate,
            }
        ).returning(MunicipalBudget.id)

        budget_id_result = await db.execute(budget_stmt)
        budget_id = budget_id_result.scalar_one()
        processed_budgets[(ine_code, data_type_str)] = budget_id

        # ── Upsert MunicipalBudgetChapter ─────────────────────────────────────
        chapter_rows = []
        for (chapter, direction_str), rec in chapters.items():
            initial  = _d(rec.initial_amount)  if rec.initial_amount  is not None else None
            final    = _d(rec.final_amount)    if rec.final_amount    is not None else None
            executed = _d(rec.executed_amount) if rec.executed_amount is not None else None

            exec_rate = _rate(executed, final or initial)
            mod_r     = _rate(_d(final) - _d(initial), initial) if initial and final else None

            chapter_rows.append({
                "municipal_budget_id": budget_id,
                "chapter":             chapter,
                "direction":           direction_str,
                "initial_amount":      initial,
                "final_amount":        final,
                "executed_amount":     executed,
                "initial_per_capita":  _per_capita(initial, population),
                "executed_per_capita": _per_capita(executed, population),
                "execution_rate":      exec_rate,
                "modification_rate":   mod_r,
            })

        if chapter_rows:
            ch_stmt = pg_insert(MunicipalBudgetChapter).values(chapter_rows).on_conflict_do_update(
                constraint="uq_mbc_chapter_dir",
                set_={
                    "initial_amount":      pg_insert(MunicipalBudgetChapter).excluded.initial_amount,
                    "final_amount":        pg_insert(MunicipalBudgetChapter).excluded.final_amount,
                    "executed_amount":     pg_insert(MunicipalBudgetChapter).excluded.executed_amount,
                    "initial_per_capita":  pg_insert(MunicipalBudgetChapter).excluded.initial_per_capita,
                    "executed_per_capita": pg_insert(MunicipalBudgetChapter).excluded.executed_per_capita,
                    "execution_rate":      pg_insert(MunicipalBudgetChapter).excluded.execution_rate,
                    "modification_rate":   pg_insert(MunicipalBudgetChapter).excluded.modification_rate,
                }
            )
            await db.execute(ch_stmt)
            result.chapters_loaded += len(chapter_rows)

        result.municipalities_loaded += 1

    # ── Cargar programas funcionales ──────────────────────────────────────────
    for (ine_code, data_type_str), area_map in programs.items():
        budget_id = processed_budgets.get((ine_code, data_type_str))
        if not budget_id:
            continue

        mun_id, mun_pop = mun_lookup.get(ine_code, (None, None))
        population = await _get_population(db, mun_id, fiscal_year) if mun_id else None

        prog_rows = []
        for area_code, rec in area_map.items():
            initial  = _d(rec.initial_amount)  if rec.initial_amount  is not None else None
            executed = _d(rec.executed_amount) if rec.executed_amount is not None else None
            prog_rows.append({
                "municipal_budget_id":  budget_id,
                "area_code":            area_code,
                "area_name":            AREA_NAMES.get(area_code, f"Área {area_code}"),
                "initial_amount":       initial,
                "executed_amount":      executed,
                "initial_per_capita":   _per_capita(initial, population),
                "executed_per_capita":  _per_capita(executed, population),
                "execution_rate":       _rate(executed, initial),
            })

        if prog_rows:
            pg_stmt = pg_insert(MunicipalBudgetProgram).values(prog_rows).on_conflict_do_update(
                constraint="uq_mbp_budget_area",
                set_={
                    "initial_amount":      pg_insert(MunicipalBudgetProgram).excluded.initial_amount,
                    "executed_amount":     pg_insert(MunicipalBudgetProgram).excluded.executed_amount,
                    "initial_per_capita":  pg_insert(MunicipalBudgetProgram).excluded.initial_per_capita,
                    "executed_per_capita": pg_insert(MunicipalBudgetProgram).excluded.executed_per_capita,
                    "execution_rate":      pg_insert(MunicipalBudgetProgram).excluded.execution_rate,
                }
            )
            await db.execute(pg_stmt)
            result.programs_loaded += len(prog_rows)

    logger.info(
        "conprel_load_done",
        year=fiscal_year,
        municipalities=result.municipalities_loaded,
        chapters=result.chapters_loaded,
        programs=result.programs_loaded,
        missing=len(result.municipalities_missing),
    )
    return result


async def refresh_comparison_view(db: AsyncSession) -> None:
    """
    Refresca la vista materializada mv_comparison_jerez.
    Usa CONCURRENTLY para no bloquear consultas en curso.
    Requiere que la vista tenga un índice único (ya creado en la migración).
    """
    logger.info("refreshing_materialized_view")
    await db.execute(text(
        "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_comparison_jerez"
    ))
    logger.info("materialized_view_refreshed")

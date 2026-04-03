"""
Resolvers para métricas de rigor y análisis de desviaciones.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from graphql.types import DeviationAnalysisType, RigorMetricsType
from models.budget import (
    BudgetLine,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    FunctionalClassification,
    OrganicClassification,
    RigorMetrics,
)

# Nombres de capítulos económicos españoles
CHAPTER_NAMES_EXPENSE = {
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
CHAPTER_NAMES_REVENUE = {
    "1": "Impuestos directos",
    "2": "Impuestos indirectos",
    "3": "Tasas y otros ingresos",
    "4": "Transferencias corrientes",
    "5": "Ingresos patrimoniales",
    "6": "Enajenación inversiones",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}


async def resolve_rigor_metrics(
    db: AsyncSession, fiscal_year: int
) -> Optional[RigorMetricsType]:
    """Devuelve las métricas de rigor más recientes del ejercicio."""
    result = await db.execute(
        select(RigorMetrics)
        .join(FiscalYear, RigorMetrics.fiscal_year_id == FiscalYear.id)
        .where(FiscalYear.year == fiscal_year)
        .order_by(RigorMetrics.computed_at.desc())
        .limit(1)
    )
    m = result.scalar_one_or_none()
    if not m:
        return None

    fy_result = await db.execute(select(FiscalYear).where(FiscalYear.year == fiscal_year))
    fy = fy_result.scalar_one_or_none()

    return RigorMetricsType(
        id=m.id,
        fiscal_year=fiscal_year,
        computed_at=m.computed_at,
        expense_execution_rate=float(m.expense_execution_rate) if m.expense_execution_rate else None,
        revenue_execution_rate=float(m.revenue_execution_rate) if m.revenue_execution_rate else None,
        modification_rate=float(m.modification_rate) if m.modification_rate else None,
        num_modifications=m.num_modifications,
        approval_delay_days=fy.approval_delay_days if fy else m.approval_delay_days,
        publication_delay_days=fy.publication_delay_days if fy else m.publication_delay_days,
        precision_index=float(m.precision_index) if m.precision_index else None,
        timeliness_index=float(m.timeliness_index) if m.timeliness_index else None,
        transparency_index=float(m.transparency_index) if m.transparency_index else None,
        global_rigor_score=float(m.global_rigor_score) if m.global_rigor_score else None,
        by_chapter=m.by_chapter,
        by_program=m.by_program,
    )


async def resolve_deviation_analysis(
    db: AsyncSession,
    fiscal_year: int,
    by: str = "chapter",
) -> list[DeviationAnalysisType]:
    """
    Análisis de desviaciones presupuestarias agregado.
    by: 'chapter' | 'program' | 'section'
    """
    # Obtener snapshot más reciente
    snap_result = await db.execute(
        select(BudgetSnapshot.id)
        .join(FiscalYear, BudgetSnapshot.fiscal_year_id == FiscalYear.id)
        .where(FiscalYear.year == fiscal_year)
        .where(BudgetSnapshot.phase == "executed")
        .order_by(BudgetSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot_id = snap_result.scalar_one_or_none()
    if not snapshot_id:
        return []

    if by == "chapter":
        return await _deviation_by_chapter(db, snapshot_id, fiscal_year)
    elif by == "program":
        return await _deviation_by_program(db, snapshot_id, fiscal_year)
    else:
        return await _deviation_by_chapter(db, snapshot_id, fiscal_year)


async def _deviation_by_chapter(
    db: AsyncSession, snapshot_id: int, fiscal_year: int
) -> list[DeviationAnalysisType]:
    result = await db.execute(
        select(
            func.substr(EconomicClassification.chapter, 1, 1).label("chapter"),
            EconomicClassification.direction.label("direction"),
            func.sum(BudgetLine.initial_credits).label("initial"),
            func.sum(BudgetLine.final_credits).label("final"),
            func.sum(BudgetLine.recognized_obligations).label("obligations"),
            func.sum(BudgetLine.initial_forecast).label("initial_fc"),
            func.sum(BudgetLine.final_forecast).label("final_fc"),
            func.sum(BudgetLine.recognized_rights).label("rights"),
        )
        .join(BudgetLine.economic)
        .where(BudgetLine.snapshot_id == snapshot_id)
        .group_by("chapter", "direction")
        .order_by("direction", "chapter")
    )
    rows = result.all()

    items = []
    for row in rows:
        is_expense = row.direction == "expense"
        initial = row.initial or Decimal("0")
        final = row.final or Decimal("0")
        executed = row.obligations or Decimal("0")
        if not is_expense:
            initial = row.initial_fc or Decimal("0")
            final = row.final_fc or Decimal("0")
            executed = row.rights or Decimal("0")

        deviation = final - executed
        deviation_pct = float(deviation / final * 100) if final > 0 else 0.0
        mod_pct = float((final - initial) / initial * 100) if initial > 0 else 0.0
        exec_rate = float(executed / final) if final > 0 else 0.0

        chapter_names = CHAPTER_NAMES_EXPENSE if is_expense else CHAPTER_NAMES_REVENUE
        name = chapter_names.get(row.chapter, f"Capítulo {row.chapter}")

        items.append(DeviationAnalysisType(
            fiscal_year=fiscal_year,
            dimension="chapter",
            code=row.chapter,
            name=f"Cap. {row.chapter} — {name} ({'Gasto' if is_expense else 'Ingreso'})",
            initial_amount=initial,
            final_amount=final,
            executed_amount=executed,
            absolute_deviation=deviation,
            deviation_pct=round(deviation_pct, 2),
            modification_pct=round(mod_pct, 2),
            execution_rate=round(exec_rate, 4),
        ))

    return items


async def _deviation_by_program(
    db: AsyncSession, snapshot_id: int, fiscal_year: int
) -> list[DeviationAnalysisType]:
    result = await db.execute(
        select(
            FunctionalClassification.program.label("program"),
            FunctionalClassification.description.label("prog_desc"),
            func.sum(BudgetLine.initial_credits).label("initial"),
            func.sum(BudgetLine.final_credits).label("final"),
            func.sum(BudgetLine.recognized_obligations).label("obligations"),
        )
        .join(BudgetLine.functional)
        .where(BudgetLine.snapshot_id == snapshot_id)
        .where(BudgetLine.final_credits > 0)
        .group_by(FunctionalClassification.program, FunctionalClassification.description)
        .order_by(func.sum(BudgetLine.final_credits).desc())
        .limit(50)
    )
    rows = result.all()

    items = []
    for row in rows:
        if not row.program:
            continue
        initial = row.initial or Decimal("0")
        final = row.final or Decimal("0")
        executed = row.obligations or Decimal("0")

        deviation = final - executed
        items.append(DeviationAnalysisType(
            fiscal_year=fiscal_year,
            dimension="program",
            code=row.program,
            name=row.prog_desc or f"Programa {row.program}",
            initial_amount=initial,
            final_amount=final,
            executed_amount=executed,
            absolute_deviation=deviation,
            deviation_pct=round(float(deviation / final * 100), 2) if final > 0 else 0.0,
            modification_pct=round(float((final - initial) / initial * 100), 2) if initial > 0 else 0.0,
            execution_rate=round(float(executed / final), 4) if final > 0 else 0.0,
        ))

    return items


async def resolve_rigor_trend(
    db: AsyncSession, years: list[int]
) -> list[RigorMetricsType]:
    """Evolución del rigor presupuestario a lo largo de varios ejercicios."""
    results = []
    for year in sorted(years):
        metrics = await resolve_rigor_metrics(db, year)
        if metrics:
            results.append(metrics)
    return results

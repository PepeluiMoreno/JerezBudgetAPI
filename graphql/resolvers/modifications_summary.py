"""
Resolvers para el resumen de modificaciones y la tendencia multi-año.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from graphql.types import ModificationsSummaryType, RigorTrendPointType
from models.budget import (
    BudgetLine,
    BudgetModification,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    RigorMetrics,
)


async def resolve_modifications_summary(
    db: AsyncSession,
    fiscal_year: int,
) -> ModificationsSummaryType:
    """
    Resumen consolidado de modificaciones de un ejercicio.
    Combina datos del XLSX (tasa de modificación) con los expedientes
    introducidos manualmente en el admin.
    """
    fy_result = await db.execute(
        select(FiscalYear).where(FiscalYear.year == fiscal_year)
    )
    fy = fy_result.scalar_one_or_none()
    fiscal_year_id = fy.id if fy else None

    # Totales por estado
    mods_result = await db.execute(
        select(BudgetModification)
        .where(BudgetModification.fiscal_year_id == fiscal_year_id)
    ) if fiscal_year_id else None

    modifications = list(mods_result.scalars().all()) if mods_result else []

    total_approved    = sum((m.total_amount or Decimal("0")) for m in modifications if m.status == "approved")
    total_in_progress = sum((m.total_amount or Decimal("0")) for m in modifications if m.status == "in_progress")

    count_approved    = sum(1 for m in modifications if m.status == "approved")
    count_in_progress = sum(1 for m in modifications if m.status == "in_progress")
    count_rejected    = sum(1 for m in modifications if m.status == "rejected")

    count_by_type: dict = {}
    for m in modifications:
        count_by_type[m.mod_type] = count_by_type.get(m.mod_type, 0) + 1

    # Tasa de modificación desde XLSX (si hay snapshot)
    mod_rate: Optional[float] = None
    if fiscal_year_id:
        snap_result = await db.execute(
            select(BudgetSnapshot.id)
            .where(BudgetSnapshot.fiscal_year_id == fiscal_year_id)
            .where(BudgetSnapshot.phase == "executed")
            .order_by(BudgetSnapshot.snapshot_date.desc())
            .limit(1)
        )
        snap_id = snap_result.scalar_one_or_none()
        if snap_id:
            agg = await db.execute(
                select(
                    func.sum(BudgetLine.initial_credits).label("initial"),
                    func.sum(BudgetLine.modifications).label("mods"),
                )
                .join(BudgetLine.economic)
                .where(BudgetLine.snapshot_id == snap_id)
                .where(EconomicClassification.direction == "expense")
            )
            row = agg.one()
            if row.initial and row.initial > 0 and row.mods is not None:
                mod_rate = round(float(row.mods / row.initial), 4)

    return ModificationsSummaryType(
        fiscal_year=fiscal_year,
        total_approved=total_approved,
        total_in_progress=total_in_progress,
        count_approved=count_approved,
        count_in_progress=count_in_progress,
        count_rejected=count_rejected,
        count_by_type=count_by_type,
        modification_rate=mod_rate,
    )


async def resolve_rigor_trend(
    db: AsyncSession,
    years: list[int],
) -> list[RigorTrendPointType]:
    """
    Serie temporal del score de rigor para los años indicados.
    Para cada año devuelve las métricas más recientes disponibles.
    Un año sin datos aparece igual con valores None (no se omite)
    para que el cliente pueda renderizar huecos en el gráfico.
    """
    points: list[RigorTrendPointType] = []

    for year in sorted(years):
        fy_result = await db.execute(
            select(FiscalYear).where(FiscalYear.year == year)
        )
        fy = fy_result.scalar_one_or_none()

        metrics_result = await db.execute(
            select(RigorMetrics)
            .join(FiscalYear, RigorMetrics.fiscal_year_id == FiscalYear.id)
            .where(FiscalYear.year == year)
            .order_by(RigorMetrics.computed_at.desc())
            .limit(1)
        ) if fy else None

        m = metrics_result.scalar_one_or_none() if metrics_result else None

        points.append(RigorTrendPointType(
            fiscal_year=year,
            is_extension=fy.is_extension if fy else False,
            global_rigor_score=float(m.global_rigor_score) if m and m.global_rigor_score else None,
            precision_index=float(m.precision_index) if m and m.precision_index else None,
            timeliness_index=float(m.timeliness_index) if m and m.timeliness_index else None,
            transparency_index=float(m.transparency_index) if m and m.transparency_index else None,
            expense_execution_rate=float(m.expense_execution_rate) if m and m.expense_execution_rate else None,
            revenue_execution_rate=float(m.revenue_execution_rate) if m and m.revenue_execution_rate else None,
            modification_rate=float(m.modification_rate) if m and m.modification_rate else None,
            approval_delay_days=fy.approval_delay_days if fy else None,
            num_modifications=m.num_modifications if m else 0,
        ))

    return points

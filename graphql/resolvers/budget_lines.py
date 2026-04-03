"""
Resolvers para consultas de líneas presupuestarias.
Soporta filtros por capítulo, programa, sección, dirección, y rango de tasa de ejecución.
La paginación es offset-based para compatibilidad con OpenBudgets viewer.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from graphql.types import BudgetLineFilter, BudgetLinePage, BudgetLineType
from models.budget import (
    BudgetLine,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    FunctionalClassification,
    OrganicClassification,
)


def _map(line: BudgetLine) -> BudgetLineType:
    eco = line.economic
    func_cls = line.functional
    org = line.organic
    return BudgetLineType(
        id=line.id,
        snapshot_id=line.snapshot_id,
        description=line.description,
        # Clasificaciones desnormalizadas
        economic_code=eco.code if eco else "",
        economic_description=eco.description if eco else "",
        chapter=eco.chapter if eco else "",
        direction=eco.direction if eco else "",
        functional_code=func_cls.code if func_cls else None,
        program_description=func_cls.description if func_cls else None,
        organic_code=org.code if org else None,
        section=org.section if org else None,
        # Gastos
        initial_credits=line.initial_credits,
        modifications=line.modifications,
        final_credits=line.final_credits,
        commitments=line.commitments,
        recognized_obligations=line.recognized_obligations,
        payments_made=line.payments_made,
        pending_payment=line.pending_payment,
        # Ingresos
        initial_forecast=line.initial_forecast,
        final_forecast=line.final_forecast,
        recognized_rights=line.recognized_rights,
        net_collection=line.net_collection,
        pending_collection=line.pending_collection,
        # Calculadas
        execution_rate=line.execution_rate,
        revenue_execution_rate=line.revenue_execution_rate,
        deviation_amount=line.deviation_amount,
        modification_rate=line.modification_rate,
    )


async def _get_latest_snapshot_id(
    db: AsyncSession,
    fiscal_year: int,
    snapshot_date: Optional[date] = None,
) -> Optional[int]:
    """Devuelve el ID del snapshot más reciente (o el de una fecha concreta)."""
    query = (
        select(BudgetSnapshot.id)
        .join(FiscalYear, BudgetSnapshot.fiscal_year_id == FiscalYear.id)
        .where(FiscalYear.year == fiscal_year)
        .where(BudgetSnapshot.phase == "executed")
    )
    if snapshot_date:
        query = query.where(BudgetSnapshot.snapshot_date == snapshot_date)
    else:
        query = query.order_by(BudgetSnapshot.snapshot_date.desc())

    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none()


async def resolve_budget_lines(
    db: AsyncSession,
    fiscal_year: int,
    filters: Optional[BudgetLineFilter] = None,
    page: int = 1,
    page_size: int = 200,
) -> BudgetLinePage:
    """
    Devuelve líneas presupuestarias paginadas con filtros opcionales.
    Por defecto usa el snapshot de ejecución más reciente disponible.
    """
    snapshot_date = None
    if filters and filters.snapshot_date is not strawberry.UNSET:
        snapshot_date = filters.snapshot_date

    snapshot_id = await _get_latest_snapshot_id(db, fiscal_year, snapshot_date)
    if snapshot_id is None:
        return BudgetLinePage(items=[], total=0, page=page, page_size=page_size, has_next=False)

    # Base query con eager loading de clasificaciones
    base_q = (
        select(BudgetLine)
        .options(
            joinedload(BudgetLine.economic),
            joinedload(BudgetLine.functional),
            joinedload(BudgetLine.organic),
        )
        .where(BudgetLine.snapshot_id == snapshot_id)
    )

    # Aplicar filtros
    if filters:
        if filters.chapter is not strawberry.UNSET and filters.chapter:
            base_q = base_q.join(BudgetLine.economic).where(
                EconomicClassification.chapter == filters.chapter
            )
        if filters.direction is not strawberry.UNSET and filters.direction:
            base_q = base_q.join(BudgetLine.economic).where(
                EconomicClassification.direction == filters.direction
            )
        if filters.functional_code is not strawberry.UNSET and filters.functional_code:
            base_q = base_q.join(BudgetLine.functional).where(
                FunctionalClassification.code.startswith(filters.functional_code)
            )
        if filters.organic_code is not strawberry.UNSET and filters.organic_code:
            base_q = base_q.join(BudgetLine.organic).where(
                OrganicClassification.code.startswith(filters.organic_code)
            )

    # Contar total
    count_q = select(func.count()).select_from(base_q.subquery())
    total = await db.scalar(count_q) or 0

    # Paginación
    offset = (page - 1) * page_size
    result = await db.execute(base_q.offset(offset).limit(page_size))
    lines = result.unique().scalars().all()

    # Filtro post-SQL por tasa de ejecución (calculada en Python)
    items = [_map(line) for line in lines]
    if filters:
        if filters.min_execution_rate is not strawberry.UNSET:
            items = [i for i in items if i.execution_rate is not None and i.execution_rate >= filters.min_execution_rate]
        if filters.max_execution_rate is not strawberry.UNSET:
            items = [i for i in items if i.execution_rate is not None and i.execution_rate <= filters.max_execution_rate]

    return BudgetLinePage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


# Importación tardía para evitar circular
import strawberry

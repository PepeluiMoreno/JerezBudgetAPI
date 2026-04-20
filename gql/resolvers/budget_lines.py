"""
Resolver para líneas presupuestarias.

Paginación offset-based compatible con OpenBudgets viewer.
Filtros aplicados a nivel SQL siempre que sea posible para eficiencia.
El filtro por tasa de ejecución se aplica en Python (campo calculado).
"""
from __future__ import annotations

import strawberry
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from gql.types import BudgetLineFilter, BudgetLinePage, BudgetLineType
from models.budget import (
    BudgetLine,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    FunctionalClassification,
    OrganicClassification,
)

_UNSET = strawberry.UNSET


def _map(line: BudgetLine) -> BudgetLineType:
    eco      = line.economic
    func_cls = line.functional
    org      = line.organic
    return BudgetLineType(
        id=line.id,
        snapshot_id=line.snapshot_id,
        description=line.description,
        economic_code=eco.code if eco else "",
        economic_description=eco.description if eco else "",
        chapter=eco.chapter if eco else "",
        direction=eco.direction if eco else "",
        functional_code=func_cls.code if func_cls else None,
        program_description=func_cls.description if func_cls else None,
        organic_code=org.code if org else None,
        section=org.section if org else None,
        initial_credits=line.initial_credits,
        modifications=line.modifications,
        final_credits=line.final_credits,
        commitments=line.commitments,
        recognized_obligations=line.recognized_obligations,
        payments_made=line.payments_made,
        pending_payment=line.pending_payment,
        initial_forecast=line.initial_forecast,
        final_forecast=line.final_forecast,
        recognized_rights=line.recognized_rights,
        net_collection=line.net_collection,
        pending_collection=line.pending_collection,
        execution_rate=line.execution_rate,
        revenue_execution_rate=line.revenue_execution_rate,
        deviation_amount=line.deviation_amount,
        modification_rate=line.modification_rate,
    )


async def _latest_snapshot_id(
    db: AsyncSession,
    fiscal_year: int,
    snapshot_date: Optional[date],
) -> Optional[int]:
    q = (
        select(BudgetSnapshot.id)
        .join(FiscalYear, BudgetSnapshot.fiscal_year_id == FiscalYear.id)
        .where(FiscalYear.year == fiscal_year)
        .where(BudgetSnapshot.phase == "executed")
    )
    if snapshot_date:
        q = q.where(BudgetSnapshot.snapshot_date == snapshot_date)
    else:
        q = q.order_by(BudgetSnapshot.snapshot_date.desc())
    result = await db.execute(q.limit(1))
    return result.scalar_one_or_none()


def _apply_sql_filters(q, filters: Optional[BudgetLineFilter]):
    if not filters:
        return q
    if filters.chapter is not _UNSET and filters.chapter:
        q = q.where(EconomicClassification.chapter == filters.chapter)
    if filters.direction is not _UNSET and filters.direction:
        q = q.where(EconomicClassification.direction == filters.direction)
    if filters.functional_code is not _UNSET and filters.functional_code:
        q = q.where(FunctionalClassification.code.startswith(filters.functional_code))
    if filters.organic_code is not _UNSET and filters.organic_code:
        q = q.where(OrganicClassification.code.startswith(filters.organic_code))
    return q


async def resolve_budget_lines(
    db: AsyncSession,
    fiscal_year: int,
    filters: Optional[BudgetLineFilter] = None,
    page: int = 1,
    page_size: int = 200,
) -> BudgetLinePage:
    snap_date = None
    if filters and filters.snapshot_date is not _UNSET:
        snap_date = filters.snapshot_date

    snapshot_id = await _latest_snapshot_id(db, fiscal_year, snap_date)
    if snapshot_id is None:
        return BudgetLinePage(items=[], total=0, page=page, page_size=page_size, has_next=False)

    base = (
        select(BudgetLine)
        .options(
            joinedload(BudgetLine.economic),
            joinedload(BudgetLine.functional),
            joinedload(BudgetLine.organic),
        )
        .join(BudgetLine.economic)
        .outerjoin(BudgetLine.functional)
        .outerjoin(BudgetLine.organic)
        .where(BudgetLine.snapshot_id == snapshot_id)
    )
    base = _apply_sql_filters(base, filters)

    count_q = select(func.count()).select_from(
        base.with_only_columns(BudgetLine.id).subquery()
    )
    total = await db.scalar(count_q) or 0

    offset = (page - 1) * page_size
    rows   = await db.execute(base.offset(offset).limit(page_size))
    lines  = rows.unique().scalars().all()

    items = [_map(line) for line in lines]

    if filters:
        if filters.min_execution_rate is not _UNSET and filters.min_execution_rate is not None:
            items = [i for i in items
                     if i.execution_rate is not None
                     and i.execution_rate >= filters.min_execution_rate]
        if filters.max_execution_rate is not _UNSET and filters.max_execution_rate is not None:
            items = [i for i in items
                     if i.execution_rate is not None
                     and i.execution_rate <= filters.max_execution_rate]

    return BudgetLinePage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )

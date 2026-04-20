"""
Resolvers para modificaciones presupuestarias.
Soporta filtros por tipo, estado y rango de fechas.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import strawberry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gql.types import BudgetModificationType
from models.budget import BudgetModification, FiscalYear


def _map(m: BudgetModification) -> BudgetModificationType:
    return BudgetModificationType(
        id=m.id,
        fiscal_year_id=m.fiscal_year_id,
        ref=m.ref,
        mod_type=m.mod_type,
        status=m.status,
        resolution_date=m.resolution_date,
        publication_date=m.publication_date,
        total_amount=m.total_amount,
        description=m.description,
        source_url=m.source_url,
    )


async def resolve_budget_modifications(
    db: AsyncSession,
    fiscal_year: int,
    mod_type: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[BudgetModificationType]:
    """
    Modificaciones presupuestarias de un ejercicio con filtros opcionales.

    Args:
        fiscal_year: Año del ejercicio
        mod_type: transfer | generate | carry_forward | supplementary | credit_reduction
        status: approved | in_progress | rejected
        from_date: Filtro desde fecha de resolución
        to_date: Filtro hasta fecha de resolución
    """
    q = (
        select(BudgetModification)
        .join(FiscalYear, BudgetModification.fiscal_year_id == FiscalYear.id)
        .where(FiscalYear.year == fiscal_year)
    )

    if mod_type:
        q = q.where(BudgetModification.mod_type == mod_type)
    if status:
        q = q.where(BudgetModification.status == status)
    if from_date:
        q = q.where(BudgetModification.resolution_date >= from_date)
    if to_date:
        q = q.where(BudgetModification.resolution_date <= to_date)

    q = q.order_by(BudgetModification.ref)
    result = await db.execute(q)
    return [_map(m) for m in result.scalars().all()]

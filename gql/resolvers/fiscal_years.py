"""
Resolvers para consultas de años fiscales.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gql.types import FiscalYearType
from models.budget import FiscalYear


def _map(fy: FiscalYear) -> FiscalYearType:
    return FiscalYearType(
        id=fy.id,
        year=fy.year,
        is_extension=fy.is_extension,
        extended_from_year=fy.extended_from_year,
        status=fy.status,
        initial_budget_date=fy.initial_budget_date,
        publication_date=fy.publication_date,
        stability_report_date=fy.stability_report_date,
        approval_delay_days=fy.approval_delay_days,
        publication_delay_days=fy.publication_delay_days,
        notes=fy.notes,
    )


async def resolve_fiscal_years(db: AsyncSession) -> list[FiscalYearType]:
    result = await db.execute(select(FiscalYear).order_by(FiscalYear.year.desc()))
    return [_map(fy) for fy in result.scalars().all()]


async def resolve_fiscal_year(db: AsyncSession, year: int) -> Optional[FiscalYearType]:
    result = await db.execute(select(FiscalYear).where(FiscalYear.year == year))
    fy = result.scalar_one_or_none()
    return _map(fy) if fy else None

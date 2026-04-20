"""
Resolvers para snapshots de ejecución presupuestaria.
Permite al cliente saber qué fechas de corte están disponibles.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gql.types import BudgetSnapshotType
from models.budget import BudgetSnapshot, FiscalYear


def _map(s: BudgetSnapshot) -> BudgetSnapshotType:
    return BudgetSnapshotType(
        id=s.id,
        fiscal_year_id=s.fiscal_year_id,
        snapshot_date=s.snapshot_date,
        phase=s.phase,
        source_url=s.source_url,
        ingested_at=s.ingested_at,
    )


async def resolve_snapshots(
    db: AsyncSession,
    fiscal_year: int,
    phase: Optional[str] = None,
) -> list[BudgetSnapshotType]:
    """Lista de snapshots disponibles para un ejercicio, más reciente primero."""
    q = (
        select(BudgetSnapshot)
        .join(FiscalYear, BudgetSnapshot.fiscal_year_id == FiscalYear.id)
        .where(FiscalYear.year == fiscal_year)
    )
    if phase:
        q = q.where(BudgetSnapshot.phase == phase)

    q = q.order_by(BudgetSnapshot.snapshot_date.desc())
    result = await db.execute(q)
    return [_map(s) for s in result.scalars().all()]

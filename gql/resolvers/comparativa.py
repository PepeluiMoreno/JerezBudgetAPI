"""
Resolver GraphQL — Comparativa CONPREL (Capa 2).
Expone grupos de pares y liquidaciones municipales para comparativa.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from models.national import (
    MunicipalBudget,
    MunicipalBudgetChapter,
    Municipality,
    PeerGroup,
    PeerGroupMember,
)


async def resolve_peer_groups(db: AsyncSession) -> list[dict]:
    """Lista de grupos de pares con conteo de miembros."""
    result = await db.execute(
        select(PeerGroup).options(selectinload(PeerGroup.members))
    )
    groups = result.scalars().all()
    return [
        {
            "id": g.id,
            "slug": g.slug,
            "name": g.name,
            "description": g.description,
            "member_count": len(g.members),
        }
        for g in groups
    ]


async def resolve_conprel_comparativa(
    db: AsyncSession,
    peer_group_slug: str,
    fiscal_year: Optional[int],
    data_type: str = "liquidation",
) -> Optional[dict]:
    """
    Devuelve las liquidaciones CONPREL de todos los municipios de un grupo de pares,
    con desglose por capítulo, para un ejercicio dado.

    Si fiscal_year es None se usa el más reciente disponible.
    """
    settings = get_settings()
    city_ine = settings.city_ine_code

    # 1. Cargar el grupo
    pg_result = await db.execute(
        select(PeerGroup).where(PeerGroup.slug == peer_group_slug)
    )
    group = pg_result.scalar_one_or_none()
    if group is None:
        return None

    # 2. INE codes de los miembros
    members_result = await db.execute(
        select(Municipality.ine_code)
        .join(PeerGroupMember, PeerGroupMember.municipality_id == Municipality.id)
        .where(PeerGroupMember.peer_group_id == group.id)
    )
    member_ine_codes = [r[0] for r in members_result.all()]
    if not member_ine_codes:
        return None

    # Asegurar que la ciudad configurada esté en la lista
    if city_ine not in member_ine_codes:
        member_ine_codes.append(city_ine)

    # 3. Años disponibles para el grupo
    years_result = await db.execute(
        select(MunicipalBudget.fiscal_year)
        .join(Municipality, Municipality.id == MunicipalBudget.municipality_id)
        .where(
            Municipality.ine_code.in_(member_ine_codes),
            MunicipalBudget.data_type == data_type,
        )
        .distinct()
        .order_by(MunicipalBudget.fiscal_year)
    )
    available_years = [r[0] for r in years_result.all()]

    if not available_years:
        return {
            "peer_group_slug": peer_group_slug,
            "peer_group_name": group.name,
            "fiscal_year": fiscal_year or 0,
            "data_type": data_type,
            "available_years": [],
            "rows": [],
        }

    target_year = fiscal_year if fiscal_year in available_years else available_years[-1]

    # 4. Cargar presupuestos del año con sus capítulos
    budgets_result = await db.execute(
        select(MunicipalBudget)
        .join(Municipality, Municipality.id == MunicipalBudget.municipality_id)
        .options(
            selectinload(MunicipalBudget.municipality),
            selectinload(MunicipalBudget.chapters),
        )
        .where(
            Municipality.ine_code.in_(member_ine_codes),
            MunicipalBudget.fiscal_year == target_year,
            MunicipalBudget.data_type == data_type,
        )
    )
    budgets = budgets_result.scalars().all()

    # 5. Ordenar por gasto ejecutado per cápita (desc) para el ranking
    def sort_key(b: MunicipalBudget):
        v = b.expense_executed_per_capita
        return float(v) if v is not None else -1.0

    budgets_sorted = sorted(budgets, key=sort_key, reverse=True)

    rows = []
    for rank, b in enumerate(budgets_sorted, start=1):
        mun = b.municipality
        chapters = [
            {
                "chapter": c.chapter,
                "direction": c.direction,
                "executed_amount": float(c.executed_amount) if c.executed_amount is not None else None,
                "executed_per_capita": float(c.executed_per_capita) if c.executed_per_capita is not None else None,
                "execution_rate": float(c.execution_rate) if c.execution_rate is not None else None,
            }
            for c in b.chapters
        ]
        rows.append({
            "ine_code": mun.ine_code,
            "name": mun.name,
            "population": mun.population,
            "is_city": mun.ine_code == city_ine,
            "total_expense_executed": float(b.total_expense_executed) if b.total_expense_executed is not None else None,
            "total_revenue_executed": float(b.total_revenue_executed) if b.total_revenue_executed is not None else None,
            "expense_executed_per_capita": float(b.expense_executed_per_capita) if b.expense_executed_per_capita is not None else None,
            "revenue_executed_per_capita": float(b.revenue_executed_per_capita) if b.revenue_executed_per_capita is not None else None,
            "expense_execution_rate": float(b.expense_execution_rate) if b.expense_execution_rate is not None else None,
            "revenue_execution_rate": float(b.revenue_execution_rate) if b.revenue_execution_rate is not None else None,
            "rank_expense_per_capita": rank,
            "chapters": chapters,
        })

    return {
        "peer_group_slug": peer_group_slug,
        "peer_group_name": group.name,
        "fiscal_year": target_year,
        "data_type": data_type,
        "available_years": available_years,
        "rows": rows,
    }

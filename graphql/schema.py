"""
Schema GraphQL raíz — S03 completo.
Todas las queries con filtros, paginación y tipos S03.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import strawberry
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter

from app.db import get_db
from graphql.types import (
    BudgetLineFilter,
    BudgetLinePage,
    BudgetModificationType,
    BudgetSnapshotType,
    DeviationAnalysisType,
    FiscalYearType,
    ModificationFilter,
    ModificationsSummaryType,
    RigorMetricsType,
    RigorTrendPointType,
)
from graphql.resolvers.fiscal_years import resolve_fiscal_years, resolve_fiscal_year
from graphql.resolvers.budget_lines import resolve_budget_lines
from graphql.resolvers.metrics import resolve_deviation_analysis, resolve_rigor_metrics
from graphql.resolvers.modifications import resolve_budget_modifications
from graphql.resolvers.modifications_summary import (
    resolve_modifications_summary,
    resolve_rigor_trend,
)
from graphql.resolvers.snapshots import resolve_snapshots


@strawberry.type
class Query:

    @strawberry.field(description="Todos los años fiscales disponibles, más reciente primero.")
    async def fiscal_years(self, info: strawberry.types.Info) -> list[FiscalYearType]:
        db: AsyncSession = info.context["db"]
        return await resolve_fiscal_years(db)

    @strawberry.field(description="Año fiscal por número de año (ej: 2025).")
    async def fiscal_year(
        self, info: strawberry.types.Info, year: int
    ) -> Optional[FiscalYearType]:
        db: AsyncSession = info.context["db"]
        return await resolve_fiscal_year(db, year)

    @strawberry.field(
        description="Snapshots de ejecución disponibles para un ejercicio, más reciente primero."
    )
    async def budget_snapshots(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
        phase: Optional[str] = None,
    ) -> list[BudgetSnapshotType]:
        db: AsyncSession = info.context["db"]
        return await resolve_snapshots(db, fiscal_year, phase)

    @strawberry.field(
        description=(
            "Líneas presupuestarias del ejercicio con paginación y filtros opcionales. "
            "Usa el snapshot más reciente salvo que se indique snapshot_date en el filtro."
        )
    )
    async def budget_lines(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
        filters: Optional[BudgetLineFilter] = None,
        page: int = 1,
        page_size: int = strawberry.argument(default=200, description="Máximo 500"),
    ) -> BudgetLinePage:
        db: AsyncSession = info.context["db"]
        page_size = min(page_size, 500)
        return await resolve_budget_lines(db, fiscal_year, filters, page, page_size)

    @strawberry.field(
        description=(
            "Modificaciones presupuestarias de un ejercicio con filtros opcionales. "
            "mod_type: transfer | generate | carry_forward | supplementary | credit_reduction. "
            "status: approved | in_progress | rejected."
        )
    )
    async def budget_modifications(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
        filters: Optional[ModificationFilter] = None,
    ) -> list[BudgetModificationType]:
        db: AsyncSession = info.context["db"]
        mod_type = None
        status   = None
        from_date = None
        to_date   = None
        if filters:
            _u = strawberry.UNSET
            mod_type  = filters.mod_type  if filters.mod_type  is not _u else None
            status    = filters.status    if filters.status    is not _u else None
            from_date = filters.from_date if filters.from_date is not _u else None
            to_date   = filters.to_date   if filters.to_date   is not _u else None
        return await resolve_budget_modifications(
            db, fiscal_year, mod_type, status, from_date, to_date
        )

    @strawberry.field(
        description=(
            "Resumen de modificaciones: totales por estado, desglose por tipo "
            "y tasa de modificación calculada desde el XLSX."
        )
    )
    async def modifications_summary(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
    ) -> ModificationsSummaryType:
        db: AsyncSession = info.context["db"]
        return await resolve_modifications_summary(db, fiscal_year)

    @strawberry.field(
        description=(
            "Métricas de rigor presupuestario del ejercicio. "
            "Incluye IPP, ITP, ITR y el Score Global de Rigor."
        )
    )
    async def rigor_metrics(
        self, info: strawberry.types.Info, fiscal_year: int
    ) -> Optional[RigorMetricsType]:
        db: AsyncSession = info.context["db"]
        return await resolve_rigor_metrics(db, fiscal_year)

    @strawberry.field(
        description=(
            "Análisis de desviaciones presupuestarias agregado. "
            "by: 'chapter' | 'program' | 'section'."
        )
    )
    async def deviation_analysis(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
        by: str = "chapter",
    ) -> list[DeviationAnalysisType]:
        db: AsyncSession = info.context["db"]
        return await resolve_deviation_analysis(db, fiscal_year, by)

    @strawberry.field(
        description=(
            "Serie temporal del rigor presupuestario para los años indicados. "
            "Los años sin datos aparecen con valores None (no se omiten). "
            "Ideal para gráficos de tendencia."
        )
    )
    async def rigor_trend(
        self,
        info: strawberry.types.Info,
        years: list[int],
    ) -> list[RigorTrendPointType]:
        db: AsyncSession = info.context["db"]
        return await resolve_rigor_trend(db, years)


# ── Context + Router ─────────────────────────────────────────────────────────

async def get_graphql_context(db=strawberry.fastapi.Depends(get_db)):
    return {"db": db}


schema = strawberry.Schema(query=Query)


def create_graphql_router() -> GraphQLRouter:
    return GraphQLRouter(
        schema=schema,
        context_getter=get_graphql_context,
        graphiql=True,
    )

"""
Schema GraphQL raíz — JerezBudget API.
Conecta todos los resolvers con el tipo Query de Strawberry.
El contexto FastAPI inyecta la sesión de base de datos en info.context["db"].
"""
from __future__ import annotations

from typing import Optional

import strawberry
from strawberry.fastapi import GraphQLRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from graphql.types import (
    BudgetLineFilter,
    BudgetLinePage,
    BudgetModificationType,
    DeviationAnalysisType,
    FiscalYearType,
    RigorMetricsType,
)
from graphql.resolvers.fiscal_years import resolve_fiscal_years, resolve_fiscal_year
from graphql.resolvers.budget_lines import resolve_budget_lines
from graphql.resolvers.metrics import (
    resolve_deviation_analysis,
    resolve_rigor_metrics,
    resolve_rigor_trend,
)


async def get_context(db: AsyncSession = strawberry.fastapi.BaseContext):
    return {"db": db}


@strawberry.type
class Query:

    @strawberry.field(description="Lista de todos los años fiscales disponibles, más reciente primero.")
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
        description=(
            "Líneas presupuestarias del ejercicio con paginación y filtros opcionales. "
            "Por defecto devuelve el snapshot de ejecución más reciente disponible."
        )
    )
    async def budget_lines(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
        filters: Optional[BudgetLineFilter] = None,
        page: int = 1,
        page_size: int = 200,
    ) -> BudgetLinePage:
        db: AsyncSession = info.context["db"]
        return await resolve_budget_lines(db, fiscal_year, filters, page, page_size)

    @strawberry.field(
        description=(
            "Métricas de rigor presupuestario para un ejercicio dado. "
            "Incluye tasas de ejecución, índices de puntualidad y score global."
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
            "by: 'chapter' (por capítulo económico) | 'program' (por programa funcional) | 'section' (por sección orgánica)"
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
        description="Evolución del rigor presupuestario a lo largo de varios ejercicios."
    )
    async def rigor_trend(
        self,
        info: strawberry.types.Info,
        years: list[int],
    ) -> list[RigorMetricsType]:
        db: AsyncSession = info.context["db"]
        return await resolve_rigor_trend(db, years)


# ── Context factory para FastAPI ─────────────────────────────────────────────

class CustomContext(strawberry.fastapi.BaseContext):
    def __init__(self, db: AsyncSession):
        self.db = db


async def get_graphql_context(db: AsyncSession = strawberry.fastapi.Depends(get_db)):
    return {"db": db}


# ── Schema y Router ──────────────────────────────────────────────────────────

schema = strawberry.Schema(
    query=Query,
    scalar_overrides={},
)


def create_graphql_router() -> GraphQLRouter:
    return GraphQLRouter(
        schema=schema,
        context_getter=get_graphql_context,
        graphiql=True,      # UI interactiva en /graphql
    )

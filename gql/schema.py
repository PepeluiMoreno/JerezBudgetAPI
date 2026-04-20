"""
Schema GraphQL raíz — S03 completo.
Todas las queries con filtros, paginación y tipos S03.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import strawberry
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter

from app.db import get_db
from gql.types import (
    BudgetLineFilter,
    BudgetLinePage,
    BudgetModificationType,
    BudgetSnapshotType,
    CuentaGeneralKpiType,
    DeviationAnalysisType,
    EtlValidationExceptionType,
    FiscalYearType,
    LiquidacionKpisType,
    LiquidacionVsCuentaGeneralType,
    ModificationFilter,
    ModificationsSummaryType,
    DeudaAnualPoint,
    MorosidadTrimPoint,
    PmpAnualPoint,
    PmpMensualPoint,
    RecaudacionChapterType,
    RecaudacionConceptType,
    RecaudacionConceptTrendPointType,
    RecaudacionKpisType,
    RecaudacionTrendPointType,
    RigorMetricsType,
    RigorTrendPointType,
    SostenibilidadResumenType,
)
from gql.resolvers.fiscal_years import resolve_fiscal_years, resolve_fiscal_year
from gql.resolvers.budget_lines import resolve_budget_lines
from gql.resolvers.metrics import resolve_deviation_analysis, resolve_rigor_metrics
from gql.resolvers.modifications import resolve_budget_modifications
from gql.resolvers.modifications_summary import (
    resolve_modifications_summary,
    resolve_rigor_trend,
)
from gql.resolvers.snapshots import resolve_snapshots
from gql.resolvers.sostenibilidad import (
    resolve_cuenta_general_years,
    resolve_cuenta_general_kpis,
    resolve_cuenta_general_trend,
    resolve_sostenibilidad_resumen,
    resolve_liquidacion_kpis,
    resolve_liquidacion_vs_cuenta_general,
    resolve_pmp_mensual,
    resolve_pmp_anual,
    resolve_deuda_historica,
    resolve_morosidad_trimestral,
)
from gql.resolvers.etl import (
    resolve_etl_exceptions,
    resolve_acknowledge_etl_exception,
)
from gql.resolvers.recaudacion import (
    resolve_recaudacion_kpis,
    resolve_recaudacion_trend,
    resolve_recaudacion_concept_trend,
)


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
        page_size: int = 200,
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

    # ── Sostenibilidad Financiera (Cuenta General) ──────────────────────────

    @strawberry.field(description="Ejercicios disponibles en Cuenta General.")
    async def cuenta_general_years(self, info: strawberry.types.Info) -> list[int]:
        db: AsyncSession = info.context["db"]
        return await resolve_cuenta_general_years(db)

    @strawberry.field(
        description="Todos los KPIs de Cuenta General de un ejercicio."
    )
    async def cuenta_general_kpis(
        self,
        info: strawberry.types.Info,
        ejercicio: int,
        nif: Optional[str] = None,
    ) -> list[CuentaGeneralKpiType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_cuenta_general_kpis(db, ejercicio, nif)
        return [
            CuentaGeneralKpiType(
                ejercicio=r.ejercicio,
                kpi=r.kpi,
                valor=r.valor,
                unidad=r.unidad,
                fuente_cuenta=r.fuente_cuenta,
            )
            for r in rows
        ]

    @strawberry.field(
        description=(
            "Resumen estructurado de sostenibilidad financiera para un ejercicio. "
            "Incluye RTGG, endeudamiento, liquidez, PMP, resultados y ratios clave."
        )
    )
    async def sostenibilidad_resumen(
        self,
        info: strawberry.types.Info,
        ejercicio: int,
        nif: Optional[str] = None,
    ) -> SostenibilidadResumenType:
        db: AsyncSession = info.context["db"]
        d = await resolve_sostenibilidad_resumen(db, ejercicio, nif)
        return SostenibilidadResumenType(**d)

    @strawberry.field(
        description=(
            "KPIs de sostenibilidad calculados desde las liquidaciones presupuestarias "
            "(transparencia.jerez.es). Cubre 2020-presente. Complementa la Cuenta General. "
            "years: lista de ejercicios (None = todos los disponibles)."
        )
    )
    async def liquidacion_kpis(
        self,
        info: strawberry.types.Info,
        years: Optional[list[int]] = None,
    ) -> list[LiquidacionKpisType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_liquidacion_kpis(db, years)
        return [LiquidacionKpisType(**r) for r in rows]

    @strawberry.field(
        description=(
            "Validación cruzada entre Cuenta General y liquidaciones presupuestarias "
            "en los años con datos en ambas fuentes (2020-2022). "
            "Útil para detectar discrepancias metodológicas."
        )
    )
    async def liquidacion_vs_cuenta_general(
        self,
        info: strawberry.types.Info,
        nif: Optional[str] = None,
    ) -> list[LiquidacionVsCuentaGeneralType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_liquidacion_vs_cuenta_general(db, nif)
        return [LiquidacionVsCuentaGeneralType(**r) for r in rows]

    @strawberry.field(
        description="Serie histórica de KPIs de Cuenta General. kpis: lista de códigos."
    )
    async def cuenta_general_trend(
        self,
        info: strawberry.types.Info,
        kpis: list[str],
        nif: Optional[str] = None,
    ) -> list[CuentaGeneralKpiType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_cuenta_general_trend(db, kpis, nif)
        return [
            CuentaGeneralKpiType(
                ejercicio=r.ejercicio,
                kpi=r.kpi,
                valor=r.valor,
                unidad=r.unidad,
                fuente_cuenta=r.fuente_cuenta,
            )
            for r in rows
        ]

    # ── Eficacia en Recaudación ─────────────────────────────────────────────────

    @strawberry.field(
        description=(
            "KPIs de recaudación de ingresos de un ejercicio, con desglose por capítulo. "
            "Requiere snapshot de fase 'executed_revenue'."
        )
    )
    async def recaudacion_kpis(
        self,
        info: strawberry.types.Info,
        fiscal_year: int,
    ) -> Optional[RecaudacionKpisType]:
        db: AsyncSession = info.context["db"]
        d = await resolve_recaudacion_kpis(db, fiscal_year)
        if d is None:
            return None
        chapters = [RecaudacionChapterType(**c) for c in d.pop("by_chapter")]
        concepts = [RecaudacionConceptType(**c) for c in d.pop("by_concept")]
        return RecaudacionKpisType(**d, by_chapter=chapters, by_concept=concepts)

    @strawberry.field(
        description=(
            "Serie histórica de KPIs de recaudación. "
            "years: lista de ejercicios (None = todos los disponibles). "
            "is_partial=true si el snapshot es anterior al 28-dic del ejercicio."
        )
    )
    async def recaudacion_trend(
        self,
        info: strawberry.types.Info,
        years: Optional[list[int]] = None,
    ) -> list[RecaudacionTrendPointType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_recaudacion_trend(db, years)
        return [RecaudacionTrendPointType(**r) for r in rows]

    @strawberry.field(
        description=(
            "Serie histórica de recaudación para un concepto económico concreto (por código). "
            "years: lista de ejercicios (None = todos los disponibles)."
        )
    )
    async def recaudacion_concept_trend(
        self,
        info: strawberry.types.Info,
        code: str,
        years: Optional[list[int]] = None,
    ) -> list[RecaudacionConceptTrendPointType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_recaudacion_concept_trend(db, code, years)
        return [RecaudacionConceptTrendPointType(**r) for r in rows]

    # ── PMP Mensual (Ley 15/2010) ───────────────────────────────────────────────

    @strawberry.field(description="PMP mensual del grupo municipal para un año.")
    async def pmp_mensual(
        self,
        info: strawberry.types.Info,
        year: int,
        ine_code: Optional[str] = None,
    ) -> list[PmpMensualPoint]:
        db: AsyncSession = info.context["db"]
        return await resolve_pmp_mensual(db, year, ine_code)

    @strawberry.field(description="Serie histórica de PMP anual por entidad del grupo.")
    async def pmp_anual(
        self,
        info: strawberry.types.Info,
        ine_code: Optional[str] = None,
    ) -> list[PmpAnualPoint]:
        db: AsyncSession = info.context["db"]
        return await resolve_pmp_anual(db, ine_code)

    # ── S12: Deuda y Morosidad ───────────────────────────────────────────────────

    @strawberry.field(
        description=(
            "Serie histórica de deuda financiera (PDF transparencia). "
            "Incluye deuda privada, ICO, total y per cápita. "
            "ine_code: código INE del municipio (None = ciudad configurada)."
        )
    )
    async def deuda_historica(
        self,
        info: strawberry.types.Info,
        ine_code: Optional[str] = None,
    ) -> list[DeudaAnualPoint]:
        db: AsyncSession = info.context["db"]
        return await resolve_deuda_historica(db, ine_code)

    @strawberry.field(
        description=(
            "Morosidad trimestral Ley 15/2010: pagos dentro/fuera de plazo, "
            "facturas pendientes e intereses de demora. "
            "year: None = todos los ejercicios disponibles."
        )
    )
    async def morosidad_trimestral(
        self,
        info: strawberry.types.Info,
        year: Optional[int] = None,
        ine_code: Optional[str] = None,
    ) -> list[MorosidadTrimPoint]:
        db: AsyncSession = info.context["db"]
        return await resolve_morosidad_trimestral(db, year, ine_code)

    @strawberry.field(
        description=(
            "Excepciones del ETL: discrepancias detectadas al cruzar fuentes de datos. "
            "Por defecto devuelve sólo las pendientes de reconocimiento."
        )
    )
    async def etl_exceptions(
        self,
        info: strawberry.types.Info,
        nif: Optional[str] = None,
        ejercicio: Optional[int] = None,
        only_pending: bool = True,
    ) -> list[EtlValidationExceptionType]:
        db: AsyncSession = info.context["db"]
        rows = await resolve_etl_exceptions(db, nif, ejercicio, only_pending)
        return [
            EtlValidationExceptionType(
                id               = r.id,
                nif_entidad      = r.nif_entidad,
                ejercicio        = r.ejercicio,
                kpi              = r.kpi,
                fuente_existente = r.fuente_existente,
                valor_existente  = r.valor_existente,
                fuente_nueva     = r.fuente_nueva,
                valor_nuevo      = r.valor_nuevo,
                diff_pct         = r.diff_pct,
                diff_abs         = r.diff_abs,
                accion           = r.accion,
                detected_at      = r.detected_at.isoformat(),
                acknowledged_at  = r.acknowledged_at.isoformat() if r.acknowledged_at else None,
                ack_notes        = r.ack_notes,
            )
            for r in rows
        ]


@strawberry.type
class Mutation:
    @strawberry.mutation(
        description="Reconoce (marca como revisada) una excepción de validación del ETL."
    )
    async def acknowledge_etl_exception(
        self,
        info: strawberry.types.Info,
        exception_id: int,
        notes: Optional[str] = None,
    ) -> EtlValidationExceptionType:
        db: AsyncSession = info.context["db"]
        r = await resolve_acknowledge_etl_exception(db, exception_id, notes)
        return EtlValidationExceptionType(
            id               = r.id,
            nif_entidad      = r.nif_entidad,
            ejercicio        = r.ejercicio,
            kpi              = r.kpi,
            fuente_existente = r.fuente_existente,
            valor_existente  = r.valor_existente,
            fuente_nueva     = r.fuente_nueva,
            valor_nuevo      = r.valor_nuevo,
            diff_pct         = r.diff_pct,
            diff_abs         = r.diff_abs,
            accion           = r.accion,
            detected_at      = r.detected_at.isoformat(),
            acknowledged_at  = r.acknowledged_at.isoformat() if r.acknowledged_at else None,
            ack_notes        = r.ack_notes,
        )


# ── Context + Router ─────────────────────────────────────────────────────────

async def get_graphql_context(db=Depends(get_db)):
    return {"db": db}


schema = strawberry.Schema(query=Query, mutation=Mutation)


def create_graphql_router() -> GraphQLRouter:
    return GraphQLRouter(
        schema=schema,
        context_getter=get_graphql_context,
        graphiql=True,
    )

"""
Tipos GraphQL (Strawberry).
Mapean los modelos ORM a tipos de la API — separación explícita
para no acoplar la API al esquema de base de datos.
"""
from __future__ import annotations

import strawberry
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@strawberry.type
class FiscalYearType:
    id: int
    year: int
    is_extension: bool
    extended_from_year: Optional[int]
    status: str
    initial_budget_date: Optional[date]
    publication_date: Optional[date]
    stability_report_date: Optional[date]
    approval_delay_days: Optional[int] = strawberry.field(
        description="Días desde el 1 de enero hasta la aprobación del presupuesto. "
                    "Negativo = aprobado antes del ejercicio. Nulo = aún no aprobado."
    )
    publication_delay_days: Optional[int] = strawberry.field(
        description="Días entre aprobación y publicación en transparencia."
    )
    notes: Optional[str]


@strawberry.type
class EconomicClassificationType:
    id: int
    code: str
    chapter: str
    article: Optional[str]
    concept: Optional[str]
    description: str
    direction: str  # expense | revenue


@strawberry.type
class FunctionalClassificationType:
    id: int
    code: str
    area: Optional[str]
    policy: Optional[str]
    program_group: Optional[str]
    program: Optional[str]
    description: str


@strawberry.type
class OrganicClassificationType:
    id: int
    code: str
    section: Optional[str]
    service: Optional[str]
    description: str


@strawberry.type
class BudgetSnapshotType:
    id: int
    fiscal_year_id: int
    snapshot_date: date
    phase: str
    source_url: Optional[str]
    ingested_at: datetime


@strawberry.type
class BudgetLineType:
    id: int
    snapshot_id: int
    description: str

    # Clasificaciones (desnormalizadas para comodidad del cliente)
    economic_code: str
    economic_description: str
    chapter: str
    direction: str  # expense | revenue
    functional_code: Optional[str]
    program_description: Optional[str]
    organic_code: Optional[str]
    section: Optional[str]

    # ── Gastos ────────────────────────────────────────────────
    initial_credits: Optional[Decimal]
    modifications: Optional[Decimal]
    final_credits: Optional[Decimal]
    commitments: Optional[Decimal]
    recognized_obligations: Optional[Decimal]
    payments_made: Optional[Decimal]
    pending_payment: Optional[Decimal]

    # ── Ingresos ──────────────────────────────────────────────
    initial_forecast: Optional[Decimal]
    final_forecast: Optional[Decimal]
    recognized_rights: Optional[Decimal]
    net_collection: Optional[Decimal]
    pending_collection: Optional[Decimal]

    # ── Métricas calculadas por línea ─────────────────────────
    execution_rate: Optional[float] = strawberry.field(
        description="obligaciones_reconocidas / créditos_definitivos"
    )
    revenue_execution_rate: Optional[float] = strawberry.field(
        description="derechos_reconocidos / previsiones_definitivas"
    )
    deviation_amount: Optional[Decimal] = strawberry.field(
        description="créditos_definitivos - obligaciones_reconocidas"
    )
    modification_rate: Optional[float] = strawberry.field(
        description="(créditos_definitivos - créditos_iniciales) / créditos_iniciales"
    )


@strawberry.type
class BudgetModificationType:
    id: int
    fiscal_year_id: int
    ref: str
    mod_type: str
    status: str
    resolution_date: Optional[date]
    publication_date: Optional[date]
    total_amount: Optional[Decimal]
    description: Optional[str]
    source_url: Optional[str]


@strawberry.type
class DeviationAnalysisType:
    """Análisis de desviación agregado por capítulo, programa o sección."""
    fiscal_year: int
    dimension: str       # chapter | program | section
    code: str
    name: str
    initial_amount: Decimal
    final_amount: Decimal
    executed_amount: Decimal
    absolute_deviation: Decimal
    deviation_pct: float = strawberry.field(
        description="(final - ejecutado) / final × 100"
    )
    modification_pct: float = strawberry.field(
        description="(final - inicial) / inicial × 100"
    )
    execution_rate: float


@strawberry.type
class ChapterMetricsType:
    chapter: str
    chapter_name: str
    initial: Decimal
    final: Decimal
    obligations: Decimal
    execution_rate: float
    modification_rate: float


@strawberry.type
class RigorMetricsType:
    id: int
    fiscal_year: int
    computed_at: datetime

    # Tasas globales
    expense_execution_rate: Optional[float] = strawberry.field(
        description="Obligaciones reconocidas / créditos definitivos (global)"
    )
    revenue_execution_rate: Optional[float] = strawberry.field(
        description="Derechos reconocidos / previsiones definitivas (global)"
    )
    modification_rate: Optional[float] = strawberry.field(
        description="(Créditos definitivos - iniciales) / iniciales (global)"
    )
    num_modifications: int

    # Puntualidad
    approval_delay_days: Optional[int]
    publication_delay_days: Optional[int]

    # Scores 0-100
    precision_index: Optional[float] = strawberry.field(
        description="IPP: 100 - |1 - tasa_ejecución| × 100, ponderado por capítulo"
    )
    timeliness_index: Optional[float] = strawberry.field(
        description="ITP: max(0, 100 - días_retraso × 0.5)"
    )
    transparency_index: Optional[float] = strawberry.field(
        description="ITR: max(0, 100 - días_publicación × 1.0)"
    )
    global_rigor_score: Optional[float] = strawberry.field(
        description="Score Global = IPP×0.5 + ITP×0.3 + ITR×0.2"
    )

    # Desgloses
    by_chapter: Optional[strawberry.scalars.JSON]
    by_program: Optional[strawberry.scalars.JSON]


# ── Tipos de paginación ──────────────────────────────────────────────────────

@strawberry.type
class BudgetLinePage:
    items: list[BudgetLineType]
    total: int
    page: int
    page_size: int
    has_next: bool


# ── Tipos de entrada (filters) ───────────────────────────────────────────────

@strawberry.input
class BudgetLineFilter:
    chapter: Optional[str] = strawberry.UNSET
    functional_code: Optional[str] = strawberry.UNSET
    organic_code: Optional[str] = strawberry.UNSET
    direction: Optional[str] = strawberry.UNSET         # expense | revenue
    min_execution_rate: Optional[float] = strawberry.UNSET
    max_execution_rate: Optional[float] = strawberry.UNSET
    snapshot_date: Optional[date] = strawberry.UNSET    # None = última disponible

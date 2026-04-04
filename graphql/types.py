"""
Tipos GraphQL (Strawberry) — versión S03 completa.
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
        description="Días desde el 1-ene hasta la aprobación. Negativo = antes del ejercicio."
    )
    publication_delay_days: Optional[int] = strawberry.field(
        description="Días entre aprobación y publicación en el portal de transparencia."
    )
    notes: Optional[str]


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
    economic_code: str
    economic_description: str
    chapter: str
    direction: str
    functional_code: Optional[str]
    program_description: Optional[str]
    organic_code: Optional[str]
    section: Optional[str]
    initial_credits: Optional[Decimal]
    modifications: Optional[Decimal]
    final_credits: Optional[Decimal]
    commitments: Optional[Decimal]
    recognized_obligations: Optional[Decimal]
    payments_made: Optional[Decimal]
    pending_payment: Optional[Decimal]
    initial_forecast: Optional[Decimal]
    final_forecast: Optional[Decimal]
    recognized_rights: Optional[Decimal]
    net_collection: Optional[Decimal]
    pending_collection: Optional[Decimal]
    execution_rate: Optional[float] = strawberry.field(
        description="obligaciones / creditos_definitivos"
    )
    revenue_execution_rate: Optional[float] = strawberry.field(
        description="derechos_reconocidos / previsiones_definitivas"
    )
    deviation_amount: Optional[Decimal] = strawberry.field(
        description="creditos_definitivos - obligaciones_reconocidas"
    )
    modification_rate: Optional[float] = strawberry.field(
        description="(creditos_definitivos - creditos_iniciales) / creditos_iniciales"
    )


@strawberry.type
class BudgetLinePage:
    items: list[BudgetLineType]
    total: int
    page: int
    page_size: int
    has_next: bool


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
class ModificationsSummaryType:
    fiscal_year: int
    total_approved: Decimal
    total_in_progress: Decimal
    count_approved: int
    count_in_progress: int
    count_rejected: int
    count_by_type: strawberry.scalars.JSON
    modification_rate: Optional[float]


@strawberry.type
class DeviationAnalysisType:
    fiscal_year: int
    dimension: str
    code: str
    name: str
    initial_amount: Decimal
    final_amount: Decimal
    executed_amount: Decimal
    absolute_deviation: Decimal
    deviation_pct: float
    modification_pct: float
    execution_rate: float


@strawberry.type
class RigorMetricsType:
    id: int
    fiscal_year: int
    computed_at: datetime
    expense_execution_rate: Optional[float]
    revenue_execution_rate: Optional[float]
    modification_rate: Optional[float]
    num_modifications: int
    approval_delay_days: Optional[int]
    publication_delay_days: Optional[int]
    precision_index: Optional[float] = strawberry.field(
        description="IPP 0-100: 100 - |1 - tasa_ejecucion| x 100, ponderado por capitulo"
    )
    timeliness_index: Optional[float] = strawberry.field(
        description="ITP 0-100: max(0, 100 - dias_retraso x 0.5). 0 si prorroga."
    )
    transparency_index: Optional[float] = strawberry.field(
        description="ITR 0-100: max(0, 100 - dias_publicacion x 1.0)"
    )
    global_rigor_score: Optional[float] = strawberry.field(
        description="Score Global = IPP*0.5 + ITP*0.3 + ITR*0.2"
    )
    by_chapter: Optional[strawberry.scalars.JSON]
    by_program: Optional[strawberry.scalars.JSON]


@strawberry.type
class RigorTrendPointType:
    fiscal_year: int
    is_extension: bool
    global_rigor_score: Optional[float]
    precision_index: Optional[float]
    timeliness_index: Optional[float]
    transparency_index: Optional[float]
    expense_execution_rate: Optional[float]
    revenue_execution_rate: Optional[float]
    modification_rate: Optional[float]
    approval_delay_days: Optional[int]
    num_modifications: int


@strawberry.input
class BudgetLineFilter:
    chapter: Optional[str] = strawberry.UNSET
    functional_code: Optional[str] = strawberry.UNSET
    organic_code: Optional[str] = strawberry.UNSET
    direction: Optional[str] = strawberry.UNSET
    min_execution_rate: Optional[float] = strawberry.UNSET
    max_execution_rate: Optional[float] = strawberry.UNSET
    snapshot_date: Optional[date] = strawberry.UNSET


@strawberry.input
class ModificationFilter:
    mod_type: Optional[str] = strawberry.UNSET
    status: Optional[str] = strawberry.UNSET
    from_date: Optional[date] = strawberry.UNSET
    to_date: Optional[date] = strawberry.UNSET

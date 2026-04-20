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


@strawberry.type
class CuentaGeneralKpiType:
    ejercicio: int
    kpi: str
    valor: Optional[Decimal]
    unidad: str
    fuente_cuenta: Optional[str]


@strawberry.type
class SostenibilidadResumenType:
    ejercicio: int
    nif_entidad: str
    remanente_tesoreria_gastos_generales: Optional[Decimal]
    remanente_tesoreria_total: Optional[Decimal]
    endeudamiento: Optional[Decimal]
    endeudamiento_habitante: Optional[Decimal]
    liquidez_inmediata: Optional[Decimal]
    liquidez_general: Optional[Decimal]
    liquidez_corto_plazo: Optional[Decimal]
    pmp_acreedores: Optional[Decimal]
    resultado_gestion_ordinaria: Optional[Decimal]
    resultado_neto_ejercicio: Optional[Decimal]
    resultado_operaciones_no_financieras: Optional[Decimal]
    activo_total: Optional[Decimal]
    pasivo_no_corriente: Optional[Decimal]
    patrimonio_neto: Optional[Decimal]
    ratio_gastos_personal: Optional[Decimal]
    ratio_ingresos_tributarios: Optional[Decimal]
    ingresos_gestion_ordinaria_cr: Optional[Decimal]
    gastos_gestion_ordinaria_cr: Optional[Decimal]
    habitantes: Optional[Decimal]
    cash_flow: Optional[Decimal]
    fuentes: Optional[str] = None  # JSON string: {kpi_code: fuente_cuenta} para los KPIs disponibles


@strawberry.type
class LiquidacionKpisType:
    """KPIs de sostenibilidad calculados desde las liquidaciones presupuestarias."""
    ejercicio: int
    snapshot_date: Optional[str]               # Fecha del snapshot utilizado (ISO 8601)
    gastos_corrientes: Optional[Decimal]
    gastos_capital: Optional[Decimal]
    gastos_financieros: Optional[Decimal]      # Capítulo III — intereses deuda
    amortizacion_deuda: Optional[Decimal]      # Capítulo IX — pasivos financieros
    gastos_totales: Optional[Decimal]
    ingresos_corrientes: Optional[Decimal]
    ingresos_capital: Optional[Decimal]
    ingresos_tributarios: Optional[Decimal]    # Capítulos I + II
    ingresos_totales: Optional[Decimal]
    estabilidad_presupuestaria: Optional[Decimal]   # ingresos_no_fin - gastos_no_fin
    resultado_presupuestario: Optional[Decimal]     # ingresos_totales - gastos_totales
    autonomia_fiscal: Optional[Decimal]             # ingresos_tributarios / ingresos_corrientes
    ratio_gastos_personal: Optional[Decimal]        # cap1 / ingresos_corrientes


@strawberry.type
class EtlValidationExceptionType:
    """Discrepancia detectada al cruzar dos fuentes para el mismo KPI."""
    id: int
    nif_entidad: str
    ejercicio: int
    kpi: str
    fuente_existente: Optional[str]
    valor_existente:  Optional[Decimal]
    fuente_nueva: Optional[str]
    valor_nuevo:  Optional[Decimal]
    diff_pct: Optional[float]
    diff_abs: Optional[Decimal]
    accion: str
    detected_at: str       # ISO datetime
    acknowledged_at: Optional[str]
    ack_notes: Optional[str]


@strawberry.type
class LiquidacionVsCuentaGeneralType:
    """Comparativa entre Cuenta General y liquidaciones presupuestarias."""
    ejercicio: int
    indicador: str
    valor_cg: Optional[Decimal]
    valor_liq: Optional[Decimal]
    diferencia_abs: Optional[Decimal]
    diferencia_pct: Optional[float]


@strawberry.type
class RecaudacionConceptType:
    code: str
    concept_name: str
    final_forecast: Decimal
    recognized_rights: Decimal
    net_collection: Decimal
    pending_collection: Decimal
    collection_rate: Optional[float]


@strawberry.type
class RecaudacionChapterType:
    chapter: str
    chapter_name: str
    initial_forecast: Optional[Decimal]
    final_forecast: Optional[Decimal]
    recognized_rights: Optional[Decimal]
    net_collection: Optional[Decimal]
    pending_collection: Optional[Decimal]
    execution_rate: Optional[float]
    collection_rate: Optional[float]
    deviation_initial_pct: Optional[float]


@strawberry.type
class RecaudacionKpisType:
    ejercicio: int
    snapshot_date: Optional[str]
    # Totales operativos Caps. I-VII (excluye operaciones financieras VIII-IX)
    total_initial_forecast: Decimal
    total_final_forecast: Decimal
    total_recognized_rights: Decimal
    total_net_collection: Decimal
    total_pending_collection: Decimal
    execution_rate: Optional[float]
    collection_rate: Optional[float]
    # Totales globales (todos los capítulos) — informativos
    total_initial_forecast_all: Decimal
    total_final_forecast_all: Decimal
    total_recognized_rights_all: Decimal
    total_net_collection_all: Decimal
    by_chapter: list[RecaudacionChapterType]
    by_concept: list[RecaudacionConceptType]


@strawberry.type
class RecaudacionConceptTrendPointType:
    ejercicio: int
    snapshot_date: Optional[str]
    is_partial: bool
    final_forecast: Decimal
    recognized_rights: Decimal
    net_collection: Decimal
    pending_collection: Decimal
    collection_rate: Optional[float]


@strawberry.type
class RecaudacionTrendPointType:
    ejercicio: int
    snapshot_date: Optional[str]
    is_partial: bool
    total_initial_forecast: Decimal
    total_final_forecast: Decimal
    total_recognized_rights: Decimal
    total_net_collection: Decimal
    total_pending_collection: Decimal
    execution_rate: Optional[float]
    collection_rate: Optional[float]


# ── S11: PMP mensual ─────────────────────────────────────────────────────────

@strawberry.type
class PmpMensualPoint:
    ejercicio: int
    mes: int
    entidad_nif: str
    entidad_nombre: str
    entidad_tipo: str
    pmp_dias: float
    alerta: str          # 'verde' | 'amarillo' | 'rojo'


@strawberry.type
class PmpAnualPoint:
    ejercicio: int
    entidad_nif: str
    entidad_nombre: str
    entidad_tipo: str
    pmp_promedio: float  # media de los meses disponibles en el año
    meses_disponibles: int
    meses_incumplimiento: int   # meses con pmp > 30 días
    alerta: str


# ── S12: Deuda y Morosidad ────────────────────────────────────────────────────

@strawberry.type
class DeudaAnualPoint:
    ejercicio: int
    deuda_viva: Optional[float]
    deuda_privada: Optional[float]
    deuda_ico: Optional[float]
    deuda_total: Optional[float]
    deuda_percapita: Optional[float]
    habitantes: Optional[int]


@strawberry.type
class MorosidadTrimPoint:
    ejercicio: int
    trimestre: str
    pmp_trimestral: Optional[float]
    pagos_plazo_count: Optional[int]
    pagos_plazo_importe: Optional[float]
    pagos_fuera_plazo_count: Optional[int]
    pagos_fuera_plazo_importe: Optional[float]
    facturas_pendientes_fuera_plazo_count: Optional[int]
    facturas_pendientes_fuera_plazo_importe: Optional[float]
    intereses_demora: Optional[float]
    ratio_fuera_plazo: Optional[float]   # derivado


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

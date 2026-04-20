"""
Resolver — Módulo Sostenibilidad Financiera.

Expone KPIs de dos fuentes:
  1. Cuenta General (rendiciondecuentas.es) — 2015-2022, KPIs contables completos
  2. Liquidaciones presupuestarias (transparencia.jerez.es) — 2020-presente,
     KPIs derivados de recognized_obligations / recognized_rights por capítulo.

La segunda fuente extiende la cobertura temporal más allá de lo publicado
en el Ministerio, utilizando los XLSX de ejecución ya cargados en budget_lines.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, distinct, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.socioeconomic import CuentaGeneralKpi
from models.budget import BudgetLine, BudgetSnapshot, FiscalYear, EconomicClassification
from app.config import get_settings


# ── KPIs clave que se incluyen en el resumen por ejercicio ───────────────────
_SUMMARY_KPIS = [
    "remanente_tesoreria_gastos_generales",
    "remanente_tesoreria_total",
    "endeudamiento",
    "endeudamiento_habitante",
    "liquidez_inmediata",
    "liquidez_general",
    "liquidez_corto_plazo",
    "pmp_acreedores",
    "resultado_gestion_ordinaria",
    "resultado_neto_ejercicio",
    "resultado_operaciones_no_financieras",
    "activo_total",
    "pasivo_no_corriente",
    "patrimonio_neto",
    "ratio_gastos_personal",
    "ratio_ingresos_tributarios",
    "ingresos_gestion_ordinaria_cr",
    "gastos_gestion_ordinaria_cr",
    "habitantes",
    "cash_flow",
]


async def resolve_cuenta_general_years(db: AsyncSession) -> list[int]:
    """Ejercicios con datos de Cuenta General para la entidad configurada."""
    s = get_settings()
    rows = await db.execute(
        select(distinct(CuentaGeneralKpi.ejercicio))
        .where(CuentaGeneralKpi.nif_entidad == s.city_nif)
        .order_by(CuentaGeneralKpi.ejercicio.desc())
    )
    return [r[0] for r in rows.fetchall()]


async def resolve_cuenta_general_kpis(
    db: AsyncSession,
    ejercicio: int,
    nif: Optional[str] = None,
) -> list[dict]:
    """
    Devuelve todos los KPIs de un ejercicio como lista de {kpi, valor, unidad}.
    Si nif=None usa el NIF configurado en settings.
    """
    s = get_settings()
    nif = nif or s.city_nif
    rows = await db.execute(
        select(CuentaGeneralKpi)
        .where(
            CuentaGeneralKpi.nif_entidad == nif,
            CuentaGeneralKpi.ejercicio == ejercicio,
        )
        .order_by(CuentaGeneralKpi.kpi)
    )
    return rows.scalars().all()


async def resolve_cuenta_general_trend(
    db: AsyncSession,
    kpis: list[str],
    nif: Optional[str] = None,
) -> list[dict]:
    """
    Serie histórica para una lista de KPI codes.
    Devuelve lista de {ejercicio, kpi, valor}.
    """
    s = get_settings()
    nif = nif or s.city_nif
    rows = await db.execute(
        select(CuentaGeneralKpi)
        .where(
            CuentaGeneralKpi.nif_entidad == nif,
            CuentaGeneralKpi.kpi.in_(kpis),
        )
        .order_by(CuentaGeneralKpi.ejercicio, CuentaGeneralKpi.kpi)
    )
    return rows.scalars().all()


async def resolve_sostenibilidad_resumen(
    db: AsyncSession,
    ejercicio: int,
    nif: Optional[str] = None,
) -> dict:
    """
    Devuelve un dict {kpi_code: valor} con los KPIs clave del ejercicio.
    Los KPIs no disponibles aparecen como None.
    """
    s = get_settings()
    nif = nif or s.city_nif
    rows = await db.execute(
        select(CuentaGeneralKpi)
        .where(
            CuentaGeneralKpi.nif_entidad == nif,
            CuentaGeneralKpi.ejercicio == ejercicio,
            CuentaGeneralKpi.kpi.in_(_SUMMARY_KPIS),
        )
    )
    kpi_rows = rows.scalars().all()
    result = {r.kpi: r.valor for r in kpi_rows}
    # Mapa de fuentes para KPIs que tengan fuente_cuenta distinta de None
    fuentes_map = {r.kpi: r.fuente_cuenta for r in kpi_rows if r.fuente_cuenta is not None}
    result["fuentes"] = json.dumps(fuentes_map) if fuentes_map else None
    # Rellenar con None los que falten
    for k in _SUMMARY_KPIS:
        result.setdefault(k, None)
    result["ejercicio"] = ejercicio
    result["nif_entidad"] = nif
    return result


# ── KPIs derivados de liquidaciones presupuestarias ──────────────────────────

async def resolve_liquidacion_kpis(
    db: AsyncSession,
    years: Optional[list[int]] = None,
) -> list[dict]:
    """
    Calcula KPIs de sostenibilidad a partir de los XLSX de liquidación
    (budget_lines) ya cargados en BD.  Cubre desde 2020 hasta el ejercicio
    más reciente disponible, complementando la Cuenta General (2015-2022).

    Para cada ejercicio con snapshots de ejecución calcula:
      - Gastos por capítulo (recognized_obligations)
      - Ingresos por capítulo (recognized_rights)
      - KPIs derivados: estabilidad, resultado, autonomía fiscal,
        gastos financieros, amortización deuda
    """

    # ── Subconsulta: último snapshot de cada (año, fase) ─────────────────────
    # Usamos el snapshot con snapshot_date más reciente (no max(id)):
    # para 2024 tenemos Feb-2024 y Dic-2024; queremos Dic-2024.
    latest_expense_subq = (
        select(
            BudgetSnapshot.fiscal_year_id,
            func.max(BudgetSnapshot.snapshot_date).label("max_date"),
        )
        .where(BudgetSnapshot.phase == "executed_expense")
        .group_by(BudgetSnapshot.fiscal_year_id)
        .subquery()
    )
    # Mapear de max_date a snap_id (necesitamos el id del snapshot más reciente)
    expense_id_subq = (
        select(BudgetSnapshot.id, BudgetSnapshot.fiscal_year_id)
        .join(
            latest_expense_subq,
            and_(
                BudgetSnapshot.fiscal_year_id == latest_expense_subq.c.fiscal_year_id,
                BudgetSnapshot.snapshot_date  == latest_expense_subq.c.max_date,
                BudgetSnapshot.phase == "executed_expense",
            ),
        )
        .subquery()
    )

    latest_revenue_subq = (
        select(
            BudgetSnapshot.fiscal_year_id,
            func.max(BudgetSnapshot.snapshot_date).label("max_date"),
        )
        .where(BudgetSnapshot.phase == "executed_revenue")
        .group_by(BudgetSnapshot.fiscal_year_id)
        .subquery()
    )
    revenue_id_subq = (
        select(BudgetSnapshot.id, BudgetSnapshot.fiscal_year_id)
        .join(
            latest_revenue_subq,
            and_(
                BudgetSnapshot.fiscal_year_id == latest_revenue_subq.c.fiscal_year_id,
                BudgetSnapshot.snapshot_date  == latest_revenue_subq.c.max_date,
                BudgetSnapshot.phase == "executed_revenue",
            ),
        )
        .subquery()
    )

    # ── Snapshot dates por año (para info de completitud) ────────────────────
    snap_date_exp_q = (
        select(FiscalYear.year, BudgetSnapshot.snapshot_date)
        .join(expense_id_subq, expense_id_subq.c.id == BudgetSnapshot.id)
        .join(FiscalYear, FiscalYear.id == BudgetSnapshot.fiscal_year_id)
    )
    snap_date_rev_q = (
        select(FiscalYear.year, BudgetSnapshot.snapshot_date)
        .join(revenue_id_subq, revenue_id_subq.c.id == BudgetSnapshot.id)
        .join(FiscalYear, FiscalYear.id == BudgetSnapshot.fiscal_year_id)
    )
    snap_dates_exp = {r.year: r.snapshot_date for r in (await db.execute(snap_date_exp_q)).fetchall()}
    snap_dates_rev = {r.year: r.snapshot_date for r in (await db.execute(snap_date_rev_q)).fetchall()}

    # ── Gastos por capítulo ───────────────────────────────────────────────────
    expense_q = (
        select(
            FiscalYear.year,
            EconomicClassification.chapter,
            func.sum(BudgetLine.recognized_obligations).label("total"),
        )
        .join(expense_id_subq, expense_id_subq.c.id == BudgetLine.snapshot_id)
        .join(BudgetSnapshot, BudgetSnapshot.id == BudgetLine.snapshot_id)
        .join(FiscalYear, FiscalYear.id == BudgetSnapshot.fiscal_year_id)
        .join(EconomicClassification, EconomicClassification.id == BudgetLine.economic_id)
        .where(EconomicClassification.direction == "expense")
        .group_by(FiscalYear.year, EconomicClassification.chapter)
        .order_by(FiscalYear.year, EconomicClassification.chapter)
    )
    if years:
        expense_q = expense_q.where(FiscalYear.year.in_(years))

    expense_rows = (await db.execute(expense_q)).fetchall()

    # ── Ingresos por capítulo ─────────────────────────────────────────────────
    revenue_q = (
        select(
            FiscalYear.year,
            EconomicClassification.chapter,
            func.sum(BudgetLine.recognized_rights).label("total"),
        )
        .join(revenue_id_subq, revenue_id_subq.c.id == BudgetLine.snapshot_id)
        .join(BudgetSnapshot, BudgetSnapshot.id == BudgetLine.snapshot_id)
        .join(FiscalYear, FiscalYear.id == BudgetSnapshot.fiscal_year_id)
        .join(EconomicClassification, EconomicClassification.id == BudgetLine.economic_id)
        .where(EconomicClassification.direction == "revenue")
        .group_by(FiscalYear.year, EconomicClassification.chapter)
        .order_by(FiscalYear.year, EconomicClassification.chapter)
    )
    if years:
        revenue_q = revenue_q.where(FiscalYear.year.in_(years))

    revenue_rows = (await db.execute(revenue_q)).fetchall()

    # ── Pivotar por año ───────────────────────────────────────────────────────
    exp: dict[int, dict[str, Decimal]] = {}
    for row in expense_rows:
        exp.setdefault(row.year, {})[row.chapter] = row.total or Decimal(0)

    rev: dict[int, dict[str, Decimal]] = {}
    for row in revenue_rows:
        rev.setdefault(row.year, {})[row.chapter] = row.total or Decimal(0)

    all_years = sorted(set(exp.keys()) | set(rev.keys()))

    results = []
    for year in all_years:
        e = exp.get(year)   # None si no hay datos de gastos para este año
        r = rev.get(year)   # None si no hay datos de ingresos para este año

        def gs(*caps) -> Optional[Decimal]:
            """Suma de capítulos de gastos. None si no hay datos de gastos."""
            if e is None:
                return None
            return sum(e.get(str(c), Decimal(0)) for c in caps)

        def rs(*caps) -> Optional[Decimal]:
            """Suma de capítulos de ingresos. None si no hay datos de ingresos."""
            if r is None:
                return None
            return sum(r.get(str(c), Decimal(0)) for c in caps)

        gastos_corrientes   = gs(1, 2, 3, 4, 5)
        gastos_capital      = gs(6, 7)
        gastos_financieros  = gs(3)
        amortizacion_deuda  = gs(9)
        gastos_totales      = gs(1, 2, 3, 4, 5, 6, 7, 8, 9)
        gastos_no_fin       = gs(1, 2, 3, 4, 5, 6, 7)

        ingresos_corrientes  = rs(1, 2, 3, 4, 5)
        ingresos_capital     = rs(6, 7)
        ingresos_tributarios = rs(1, 2)
        ingresos_totales     = rs(1, 2, 3, 4, 5, 6, 7, 8, 9)
        ingresos_no_fin      = rs(1, 2, 3, 4, 5, 6, 7)

        # Estabilidad: solo si tenemos ambas partes
        if ingresos_no_fin is not None and gastos_no_fin is not None:
            estabilidad = ingresos_no_fin - gastos_no_fin
        elif ingresos_no_fin is not None:
            estabilidad = None   # gastos pendientes de cargar
        else:
            estabilidad = None

        # Resultado presupuestario total
        if ingresos_totales is not None and gastos_totales is not None:
            resultado_presupuestario = ingresos_totales - gastos_totales
        else:
            resultado_presupuestario = None

        # Autonomía fiscal
        autonomia_fiscal = (
            ingresos_tributarios / ingresos_corrientes
            if ingresos_corrientes else None
        )

        # Ratio gastos personal
        cap1 = gs(1)
        ratio_gastos_personal = (
            cap1 / ingresos_corrientes
            if (cap1 is not None and ingresos_corrientes) else None
        )

        # Fecha del snapshot más reciente disponible (gastos o ingresos)
        snap_date = snap_dates_exp.get(year) or snap_dates_rev.get(year)

        results.append({
            "ejercicio": year,
            "gastos_corrientes": gastos_corrientes,
            "gastos_capital": gastos_capital,
            "gastos_financieros": gastos_financieros,
            "amortizacion_deuda": amortizacion_deuda,
            "gastos_totales": gastos_totales,
            "ingresos_corrientes": ingresos_corrientes,
            "ingresos_capital": ingresos_capital,
            "ingresos_tributarios": ingresos_tributarios,
            "ingresos_totales": ingresos_totales,
            "estabilidad_presupuestaria": estabilidad,
            "resultado_presupuestario": resultado_presupuestario,
            "autonomia_fiscal": autonomia_fiscal,
            "ratio_gastos_personal": ratio_gastos_personal,
            "snapshot_date": snap_date.isoformat() if snap_date else None,
        })

    return results


async def resolve_liquidacion_vs_cuenta_general(
    db: AsyncSession,
    nif: Optional[str] = None,
) -> list[dict]:
    """
    Compara KPIs de sostenibilidad entre las dos fuentes en los años solapados.
    Útil para detectar discrepancias metodológicas o errores de carga.

    Años solapados: aquellos con datos tanto en cuenta_general_kpis como en budget_lines.
    Devuelve lista de {ejercicio, indicador, valor_cg, valor_liq, diferencia_abs, diferencia_pct}.
    """
    import structlog
    log = structlog.get_logger(__name__)

    s = get_settings()
    nif = nif or s.city_nif

    # Obtener KPIs de Cuenta General para todos los ejercicios disponibles
    cg_rows = await db.execute(
        select(CuentaGeneralKpi)
        .where(
            CuentaGeneralKpi.nif_entidad == nif,
            CuentaGeneralKpi.kpi.in_([
                "gastos_gestion_ordinaria_cr",
                "ingresos_gestion_ordinaria_cr",
                "resultado_operaciones_no_financieras",
                "ratio_gastos_personal",
                "ratio_ingresos_tributarios",
            ]),
        )
        .order_by(CuentaGeneralKpi.ejercicio)
    )
    cg_by_year: dict[int, dict[str, Decimal]] = {}
    for r in cg_rows.scalars().all():
        cg_by_year.setdefault(r.ejercicio, {})[r.kpi] = r.valor

    # Obtener KPIs de liquidaciones para los mismos años
    liq_years = list(cg_by_year.keys())
    if not liq_years:
        return []

    liq_rows = await resolve_liquidacion_kpis(db, liq_years)
    liq_by_year = {r["ejercicio"]: r for r in liq_rows}

    # Mapeo CG → liquidación para la comparación
    _COMPARE = {
        "gastos_gestion_ordinaria_cr":           "gastos_corrientes",
        "ingresos_gestion_ordinaria_cr":          "ingresos_corrientes",
        "resultado_operaciones_no_financieras":   "estabilidad_presupuestaria",
        "ratio_gastos_personal":                  "ratio_gastos_personal",
        "ratio_ingresos_tributarios":             "autonomia_fiscal",
    }

    comparisons = []
    for year in sorted(set(cg_by_year.keys()) & set(liq_by_year.keys())):
        cg = cg_by_year[year]
        liq = liq_by_year[year]
        for kpi_cg, kpi_liq in _COMPARE.items():
            v_cg = cg.get(kpi_cg)
            v_liq = liq.get(kpi_liq)
            if v_cg is None or v_liq is None:
                continue
            diff_abs = float(v_liq) - float(v_cg)
            diff_pct = (diff_abs / float(v_cg) * 100) if v_cg != 0 else None
            comparisons.append({
                "ejercicio": year,
                "indicador": kpi_cg,
                "valor_cg": v_cg,
                "valor_liq": v_liq,
                "diferencia_abs": Decimal(str(round(diff_abs, 2))),
                "diferencia_pct": round(diff_pct, 2) if diff_pct is not None else None,
            })
            if diff_pct is not None and abs(diff_pct) > 5:
                log.warning(
                    "cross_source_discrepancy",
                    year=year,
                    kpi=kpi_cg,
                    cg=float(v_cg),
                    liq=float(v_liq),
                    diff_pct=round(diff_pct, 2),
                )

    return comparisons


# ── S11: PMP mensual ─────────────────────────────────────────────────────────

from gql.types import PmpMensualPoint, PmpAnualPoint

_PMP_VERDE    = 30.0
_PMP_AMARILLO = 60.0

def _pmp_alerta(dias: float) -> str:
    if dias <= _PMP_VERDE:
        return "verde"
    if dias <= _PMP_AMARILLO:
        return "amarillo"
    return "rojo"


async def resolve_pmp_mensual(
    db: AsyncSession,
    year: int,
    ine_code: Optional[str] = None,
) -> list[PmpMensualPoint]:
    """
    PMP mensual de todas las entidades del grupo municipal en el año indicado.
    Combina datos de cuenta_general_kpis (periodo='01'–'12', kpi='pmp_ayto')
    con el catálogo municipal_entities para enriquecer con nombre y tipo.
    """
    from models.budget import MunicipalEntity

    s = get_settings()
    ine_code = ine_code or s.city_ine_code

    # Carga entidades del municipio
    ent_rows = await db.execute(
        select(MunicipalEntity).where(MunicipalEntity.ine_code == ine_code)
    )
    entities = {e.nif: e for e in ent_rows.scalars().all()}

    # Carga KPIs PMP mensuales
    kpi_rows = await db.execute(
        select(CuentaGeneralKpi).where(
            CuentaGeneralKpi.ejercicio == year,
            CuentaGeneralKpi.kpi      == "pmp_ayto",
            CuentaGeneralKpi.periodo  != "",
        ).order_by(CuentaGeneralKpi.nif_entidad, CuentaGeneralKpi.periodo)
    )

    result: list[PmpMensualPoint] = []
    for kpi in kpi_rows.scalars().all():
        ent = entities.get(kpi.nif_entidad)
        dias = float(kpi.valor or 0)
        result.append(PmpMensualPoint(
            ejercicio      = kpi.ejercicio,
            mes            = int(kpi.periodo),
            entidad_nif    = kpi.nif_entidad,
            entidad_nombre = ent.nombre if ent else kpi.nif_entidad,
            entidad_tipo   = ent.tipo   if ent else "desconocido",
            pmp_dias       = dias,
            alerta         = _pmp_alerta(dias),
        ))
    return result


async def resolve_pmp_anual(
    db: AsyncSession,
    ine_code: Optional[str] = None,
) -> list[PmpAnualPoint]:
    """
    Serie histórica de PMP anual (promedio mensual) por entidad.
    Útil para el gráfico de tendencia en PmpView.
    """
    from models.budget import MunicipalEntity

    s = get_settings()
    ine_code = ine_code or s.city_ine_code

    ent_rows = await db.execute(
        select(MunicipalEntity).where(MunicipalEntity.ine_code == ine_code)
    )
    entities = {e.nif: e for e in ent_rows.scalars().all()}

    rows = await db.execute(
        select(
            CuentaGeneralKpi.nif_entidad,
            CuentaGeneralKpi.ejercicio,
            func.avg(CuentaGeneralKpi.valor).label("pmp_promedio"),
            func.count(CuentaGeneralKpi.id).label("meses"),
            func.count(
                CuentaGeneralKpi.id
            ).filter(CuentaGeneralKpi.valor > _PMP_VERDE).label("incumplimientos"),
        ).where(
            CuentaGeneralKpi.kpi     == "pmp_ayto",
            CuentaGeneralKpi.periodo != "",
        ).group_by(
            CuentaGeneralKpi.nif_entidad,
            CuentaGeneralKpi.ejercicio,
        ).order_by(
            CuentaGeneralKpi.nif_entidad,
            CuentaGeneralKpi.ejercicio,
        )
    )

    result: list[PmpAnualPoint] = []
    for r in rows.all():
        ent = entities.get(r.nif_entidad)
        promedio = float(r.pmp_promedio or 0)
        result.append(PmpAnualPoint(
            ejercicio            = r.ejercicio,
            entidad_nif          = r.nif_entidad,
            entidad_nombre       = ent.nombre if ent else r.nif_entidad,
            entidad_tipo         = ent.tipo   if ent else "desconocido",
            pmp_promedio         = round(promedio, 1),
            meses_disponibles    = int(r.meses),
            meses_incumplimiento = int(r.incumplimientos),
            alerta               = _pmp_alerta(promedio),
        ))
    return result


# ── S12: Deuda financiera histórica ──────────────────────────────────────────

async def resolve_deuda_historica(
    db: AsyncSession,
    ine_code: Optional[str] = None,
) -> list:
    from gql.types import DeudaAnualPoint
    from models.national import MunicipalPopulation, Municipality

    cfg = get_settings()
    nif = cfg.city_nif

    # Deuda financiera PDF (fuente transparencia): kpis deuda_privada, deuda_ico, deuda_total
    rows = await db.execute(
        select(
            CuentaGeneralKpi.ejercicio,
            CuentaGeneralKpi.kpi,
            CuentaGeneralKpi.valor,
        ).where(
            CuentaGeneralKpi.nif_entidad == nif,
            CuentaGeneralKpi.kpi.in_(["deuda_privada", "deuda_ico", "deuda_total", "deuda_viva"]),
            CuentaGeneralKpi.periodo == "",
        ).order_by(CuentaGeneralKpi.ejercicio)
    )

    # Población por año para per cápita — join Municipality → MunicipalPopulation
    _ine = ine_code or cfg.city_ine_code
    pop_rows = await db.execute(
        select(MunicipalPopulation.year, MunicipalPopulation.population)
        .join(Municipality, Municipality.id == MunicipalPopulation.municipality_id)
        .where(Municipality.ine_code == _ine)
        .order_by(MunicipalPopulation.year)
    )
    pop_map = {r.year: r.population for r in pop_rows.all()}

    # Pivota por ejercicio
    by_year: dict[int, dict] = {}
    for r in rows.all():
        d = by_year.setdefault(r.ejercicio, {})
        d[r.kpi] = float(r.valor) if r.valor is not None else None

    result = []
    for year in sorted(by_year):
        d = by_year[year]
        total = d.get("deuda_total") or d.get("deuda_viva")
        hab   = pop_map.get(year)
        result.append(DeudaAnualPoint(
            ejercicio       = year,
            deuda_viva      = d.get("deuda_viva"),
            deuda_privada   = d.get("deuda_privada"),
            deuda_ico       = d.get("deuda_ico"),
            deuda_total     = total,
            deuda_percapita = round(total / hab, 2) if (total and hab) else None,
            habitantes      = hab,
        ))
    return result


# ── S12: Morosidad trimestral ─────────────────────────────────────────────────

_MOROSIDAD_KPIS = [
    "pmp_trimestral",
    "pagos_plazo_count",
    "pagos_plazo_importe",
    "pagos_fuera_plazo_count",
    "pagos_fuera_plazo_importe",
    "facturas_pendientes_fuera_plazo_count",
    "facturas_pendientes_fuera_plazo_importe",
    "intereses_demora",
]


async def resolve_morosidad_trimestral(
    db: AsyncSession,
    year: Optional[int] = None,
    ine_code: Optional[str] = None,
) -> list:
    from gql.types import MorosidadTrimPoint

    cfg = get_settings()
    nif = cfg.city_nif

    conditions = [
        CuentaGeneralKpi.nif_entidad == nif,
        CuentaGeneralKpi.kpi.in_(_MOROSIDAD_KPIS),
        CuentaGeneralKpi.periodo.in_(["T1", "T2", "T3", "T4"]),
    ]
    if year:
        conditions.append(CuentaGeneralKpi.ejercicio == year)

    rows = await db.execute(
        select(
            CuentaGeneralKpi.ejercicio,
            CuentaGeneralKpi.periodo,
            CuentaGeneralKpi.kpi,
            CuentaGeneralKpi.valor,
        ).where(*conditions).order_by(
            CuentaGeneralKpi.ejercicio,
            CuentaGeneralKpi.periodo,
        )
    )

    # Pivota por (ejercicio, trimestre)
    by_key: dict[tuple, dict] = {}
    for r in rows.all():
        key = (r.ejercicio, r.periodo)
        d = by_key.setdefault(key, {})
        d[r.kpi] = float(r.valor) if r.valor is not None else None

    result = []
    for (ejercicio, trimestre) in sorted(by_key):
        d = by_key[(ejercicio, trimestre)]
        dentro  = d.get("pagos_plazo_importe")   or 0
        fuera   = d.get("pagos_fuera_plazo_importe") or 0
        total   = dentro + fuera
        ratio   = round(fuera / total, 4) if total > 0 else None
        result.append(MorosidadTrimPoint(
            ejercicio                                = ejercicio,
            trimestre                                = trimestre,
            pmp_trimestral                           = d.get("pmp_trimestral"),
            pagos_plazo_count                        = int(d["pagos_plazo_count"]) if d.get("pagos_plazo_count") is not None else None,
            pagos_plazo_importe                      = d.get("pagos_plazo_importe"),
            pagos_fuera_plazo_count                  = int(d["pagos_fuera_plazo_count"]) if d.get("pagos_fuera_plazo_count") is not None else None,
            pagos_fuera_plazo_importe                = d.get("pagos_fuera_plazo_importe"),
            facturas_pendientes_fuera_plazo_count    = int(d["facturas_pendientes_fuera_plazo_count"]) if d.get("facturas_pendientes_fuera_plazo_count") is not None else None,
            facturas_pendientes_fuera_plazo_importe  = d.get("facturas_pendientes_fuera_plazo_importe"),
            intereses_demora                         = d.get("intereses_demora"),
            ratio_fuera_plazo                        = ratio,
        ))
    return result

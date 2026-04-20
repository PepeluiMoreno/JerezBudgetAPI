"""
Resolver — Eficacia en Recaudación de Ingresos.

Calcula KPIs de recaudación desde los XLSX de ejecución de ingresos
ya cargados en budget_lines (phase = executed_revenue).

KPIs:
  - Tasa de ejecución   = derechos_reconocidos / previsiones_definitivas
  - Tasa de recaudación = recaudación_neta / derechos_reconocidos
  - Pendientes de cobro = derechos_reconocidos - recaudación_neta
  - Desviación inicial  = (previsiones_definitivas - previsiones_iniciales) / previsiones_iniciales
  Todo por año y desglosado por capítulo (caps I–IX).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.budget import BudgetLine, BudgetSnapshot, FiscalYear, EconomicClassification

_CHAPTER_NAMES = {
    "1": "Impuestos directos",
    "2": "Impuestos indirectos",
    "3": "Tasas y otros ingresos",
    "4": "Transferencias corrientes",
    "5": "Ingresos patrimoniales",
    "6": "Enajenación de inversiones",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}


def _rate(num: Optional[Decimal], den: Optional[Decimal]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return float(num / den)


async def resolve_recaudacion_kpis(
    db: AsyncSession,
    fiscal_year: int,
) -> Optional[dict]:
    """KPIs de recaudación de un ejercicio con desglose por capítulo."""

    # Snapshot más reciente de executed_revenue para el año
    snap_subq = (
        select(
            BudgetSnapshot.id,
            BudgetSnapshot.snapshot_date,
        )
        .join(FiscalYear, FiscalYear.id == BudgetSnapshot.fiscal_year_id)
        .where(
            FiscalYear.year == fiscal_year,
            BudgetSnapshot.phase == "executed_revenue",
        )
        .order_by(BudgetSnapshot.snapshot_date.desc())
        .limit(1)
        .subquery()
    )

    # Totales por capítulo
    # Previsión definitiva: si el XLSX incluye la columna "previsiones definitivas" se usa
    # directamente. Si no (formato XLS 2023), se reconstruye como inicial + modificaciones.
    # COALESCE(modifications, 0) porque en XLSX más nuevos modifications es NULL para ingresos.
    _eff_final = func.coalesce(
        BudgetLine.final_forecast,
        BudgetLine.initial_forecast + func.coalesce(BudgetLine.modifications, 0),
    )
    q = (
        select(
            EconomicClassification.chapter,
            func.sum(BudgetLine.initial_forecast).label("initial_forecast"),
            func.sum(_eff_final).label("final_forecast"),
            func.sum(BudgetLine.recognized_rights).label("recognized_rights"),
            func.sum(BudgetLine.net_collection).label("net_collection"),
            func.sum(BudgetLine.pending_collection).label("pending_collection"),
        )
        .join(snap_subq, snap_subq.c.id == BudgetLine.snapshot_id)
        .join(EconomicClassification, EconomicClassification.id == BudgetLine.economic_id)
        .where(EconomicClassification.direction == "revenue")
        .group_by(EconomicClassification.chapter)
        .order_by(EconomicClassification.chapter)
    )

    rows = (await db.execute(q)).fetchall()
    if not rows:
        return None

    # ── Query por concepto (ingresos de gestión propia: caps 1-3 y 5) ────────
    # Excluye transferencias (4, 7) y operaciones financieras (6, 8, 9)
    _eff_final_c = func.coalesce(
        BudgetLine.final_forecast,
        BudgetLine.initial_forecast + func.coalesce(BudgetLine.modifications, 0),
    )
    q_concepts = (
        select(
            EconomicClassification.code,
            EconomicClassification.description,
            func.sum(_eff_final_c).label("final_forecast"),
            func.sum(BudgetLine.recognized_rights).label("recognized_rights"),
            func.sum(BudgetLine.net_collection).label("net_collection"),
            func.sum(BudgetLine.pending_collection).label("pending_collection"),
        )
        .join(snap_subq, snap_subq.c.id == BudgetLine.snapshot_id)
        .join(EconomicClassification, EconomicClassification.id == BudgetLine.economic_id)
        .where(
            EconomicClassification.direction == "revenue",
            EconomicClassification.chapter.in_(["1", "2", "3", "5"]),
        )
        .group_by(EconomicClassification.code, EconomicClassification.description)
        .order_by(func.sum(BudgetLine.recognized_rights).desc())
    )
    concept_rows = (await db.execute(q_concepts)).fetchall()

    # Fecha del snapshot usado
    snap_date_row = (await db.execute(
        select(BudgetSnapshot.snapshot_date)
        .join(FiscalYear, FiscalYear.id == BudgetSnapshot.fiscal_year_id)
        .where(
            FiscalYear.year == fiscal_year,
            BudgetSnapshot.phase == "executed_revenue",
        )
        .order_by(BudgetSnapshot.snapshot_date.desc())
        .limit(1)
    )).scalar()

    chapters = []
    tot_ini = tot_fin = tot_rec = tot_net = tot_pend = Decimal(0)
    # Totales operativos: excluyen Caps. VIII y IX (operaciones financieras)
    op_ini = op_fin = op_rec = op_net = op_pend = Decimal(0)

    for r in rows:
        ini  = r.initial_forecast  or Decimal(0)
        fin  = r.final_forecast    or Decimal(0)
        rec  = r.recognized_rights or Decimal(0)
        net  = r.net_collection    or Decimal(0)
        pend = r.pending_collection if r.pending_collection is not None else (rec - net)

        tot_ini  += ini
        tot_fin  += fin
        tot_rec  += rec
        tot_net  += net
        tot_pend += pend

        if r.chapter not in ("8", "9"):
            op_ini  += ini
            op_fin  += fin
            op_rec  += rec
            op_net  += net
            op_pend += pend

        chapters.append({
            "chapter":          r.chapter,
            "chapter_name":     _CHAPTER_NAMES.get(r.chapter, f"Capítulo {r.chapter}"),
            "initial_forecast": ini,
            "final_forecast":   fin,
            "recognized_rights": rec,
            "net_collection":   net,
            "pending_collection": pend,
            "execution_rate":   _rate(rec, fin),
            "collection_rate":  _rate(net, rec),
            "deviation_initial_pct": _rate(fin - ini, ini) if ini else None,
        })

    return {
        "ejercicio":               fiscal_year,
        "snapshot_date":           snap_date_row.isoformat() if snap_date_row else None,
        # Totales operativos (Caps. I-VII) — usados en los KPIs principales
        "total_initial_forecast":  op_ini,
        "total_final_forecast":    op_fin,
        "total_recognized_rights": op_rec,
        "total_net_collection":    op_net,
        "total_pending_collection": op_pend,
        "execution_rate":  _rate(op_rec, op_fin),
        "collection_rate": _rate(op_net, op_rec),
        # Totales globales (todos los capítulos) — informativos
        "total_initial_forecast_all":  tot_ini,
        "total_final_forecast_all":    tot_fin,
        "total_recognized_rights_all": tot_rec,
        "total_net_collection_all":    tot_net,
        "by_chapter":  chapters,
        "by_concept":  [
            {
                "code":               r.code,
                "concept_name":       r.description,
                "final_forecast":     r.final_forecast or Decimal(0),
                "recognized_rights":  r.recognized_rights or Decimal(0),
                "net_collection":     r.net_collection or Decimal(0),
                "pending_collection": (
                    r.pending_collection if r.pending_collection is not None
                    else (r.recognized_rights or Decimal(0)) - (r.net_collection or Decimal(0))
                ),
                "collection_rate": _rate(
                    r.net_collection or Decimal(0),
                    r.recognized_rights or Decimal(0),
                ),
            }
            for r in concept_rows
            if (r.recognized_rights or 0) > 0
        ],
    }


async def resolve_recaudacion_trend(
    db: AsyncSession,
    years: Optional[list[int]] = None,
) -> list[dict]:
    """
    Serie histórica de KPIs de recaudación.
    Devuelve un punto por ejercicio con datos en BD.
    """
    # Último snapshot executed_revenue de cada año
    latest_subq = (
        select(
            BudgetSnapshot.fiscal_year_id,
            func.max(BudgetSnapshot.snapshot_date).label("max_date"),
        )
        .where(BudgetSnapshot.phase == "executed_revenue")
        .group_by(BudgetSnapshot.fiscal_year_id)
        .subquery()
    )
    snap_id_subq = (
        select(BudgetSnapshot.id, BudgetSnapshot.fiscal_year_id, BudgetSnapshot.snapshot_date)
        .join(latest_subq, and_(
            BudgetSnapshot.fiscal_year_id == latest_subq.c.fiscal_year_id,
            BudgetSnapshot.snapshot_date  == latest_subq.c.max_date,
            BudgetSnapshot.phase == "executed_revenue",
        ))
        .subquery()
    )

    q = (
        select(
            FiscalYear.year,
            snap_id_subq.c.snapshot_date,
            func.sum(BudgetLine.initial_forecast).label("ini"),
            func.sum(
                func.coalesce(
                    BudgetLine.final_forecast,
                    BudgetLine.initial_forecast + func.coalesce(BudgetLine.modifications, 0),
                )
            ).label("fin"),
            func.sum(BudgetLine.recognized_rights).label("rec"),
            func.sum(BudgetLine.net_collection).label("net"),
            func.sum(BudgetLine.pending_collection).label("pend"),
        )
        .join(snap_id_subq, snap_id_subq.c.id == BudgetLine.snapshot_id)
        .join(BudgetSnapshot, BudgetSnapshot.id == BudgetLine.snapshot_id)
        .join(FiscalYear, FiscalYear.id == snap_id_subq.c.fiscal_year_id)
        .join(EconomicClassification, EconomicClassification.id == BudgetLine.economic_id)
        .where(
            EconomicClassification.direction == "revenue",
            EconomicClassification.chapter.not_in(["8", "9"]),
        )
        .group_by(FiscalYear.year, snap_id_subq.c.snapshot_date)
        .order_by(FiscalYear.year)
    )
    if years:
        q = q.where(FiscalYear.year.in_(years))

    rows = (await db.execute(q)).fetchall()

    results = []
    for r in rows:
        fin  = r.fin or Decimal(0)
        rec  = r.rec or Decimal(0)
        net  = r.net or Decimal(0)
        ini  = r.ini or Decimal(0)
        pend = r.pend if r.pend is not None else (rec - net)

        snap = r.snapshot_date
        # Parcial solo si el snapshot es del mismo año fiscal y no es de final de diciembre
        is_partial = snap and snap.year == r.year and (snap.month < 12 or snap.day < 28)

        results.append({
            "ejercicio":               r.year,
            "snapshot_date":           snap.isoformat() if snap else None,
            "is_partial":              is_partial,
            "total_initial_forecast":  ini,
            "total_final_forecast":    fin,
            "total_recognized_rights": rec,
            "total_net_collection":    net,
            "total_pending_collection": pend,
            "execution_rate":  _rate(rec, fin),
            "collection_rate": _rate(net, rec),
        })

    return results


async def resolve_recaudacion_concept_trend(
    db: AsyncSession,
    code: str,
    years: Optional[list[int]] = None,
) -> list[dict]:
    """Serie histórica de un concepto recaudatorio concreto."""
    latest_subq = (
        select(
            BudgetSnapshot.fiscal_year_id,
            func.max(BudgetSnapshot.snapshot_date).label("max_date"),
        )
        .where(BudgetSnapshot.phase == "executed_revenue")
        .group_by(BudgetSnapshot.fiscal_year_id)
        .subquery()
    )
    snap_id_subq = (
        select(BudgetSnapshot.id, BudgetSnapshot.fiscal_year_id, BudgetSnapshot.snapshot_date)
        .join(latest_subq, and_(
            BudgetSnapshot.fiscal_year_id == latest_subq.c.fiscal_year_id,
            BudgetSnapshot.snapshot_date  == latest_subq.c.max_date,
            BudgetSnapshot.phase == "executed_revenue",
        ))
        .subquery()
    )

    _eff_final = func.coalesce(
        BudgetLine.final_forecast,
        BudgetLine.initial_forecast + func.coalesce(BudgetLine.modifications, 0),
    )
    q = (
        select(
            FiscalYear.year,
            snap_id_subq.c.snapshot_date,
            func.sum(_eff_final).label("fin"),
            func.sum(BudgetLine.recognized_rights).label("rec"),
            func.sum(BudgetLine.net_collection).label("net"),
            func.sum(BudgetLine.pending_collection).label("pend"),
        )
        .join(snap_id_subq, snap_id_subq.c.id == BudgetLine.snapshot_id)
        .join(FiscalYear, FiscalYear.id == snap_id_subq.c.fiscal_year_id)
        .join(EconomicClassification, EconomicClassification.id == BudgetLine.economic_id)
        .where(
            EconomicClassification.direction == "revenue",
            EconomicClassification.code == code,
        )
        .group_by(FiscalYear.year, snap_id_subq.c.snapshot_date)
        .order_by(FiscalYear.year)
    )
    if years:
        q = q.where(FiscalYear.year.in_(years))

    rows = (await db.execute(q)).fetchall()
    results = []
    for r in rows:
        fin  = r.fin or Decimal(0)
        rec  = r.rec or Decimal(0)
        net  = r.net or Decimal(0)
        pend = r.pend if r.pend is not None else (rec - net)
        snap = r.snapshot_date
        is_partial = snap and snap.year == r.year and (snap.month < 12 or snap.day < 28)
        results.append({
            "ejercicio":          r.year,
            "snapshot_date":      snap.isoformat() if snap else None,
            "is_partial":         is_partial,
            "final_forecast":     fin,
            "recognized_rights":  rec,
            "net_collection":     net,
            "pending_collection": pend,
            "collection_rate":    _rate(net, rec),
        })
    return results

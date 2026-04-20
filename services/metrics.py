"""
Servicio de cálculo de métricas de rigor presupuestario.

Índices calculados:
  IPP — Índice de Precisión Presupuestaria
        100 - |1 - tasa_ejecución_gastos| × 100
        Penaliza tanto subejecución como sobreejecución.

  ITP — Índice de Puntualidad
        max(0, 100 - días_retraso_aprobación × 0.5)
        0 días = 100 puntos. Prórroga = 0 puntos (penalty máximo).

  ITR — Índice de Transparencia
        max(0, 100 - días_retraso_publicación × 1.0)
        Mide la rapidez en publicar en el portal de transparencia.

  Score Global = IPP × 0.50 + ITP × 0.30 + ITR × 0.20
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.budget import (
    BudgetLine,
    BudgetModification,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    FunctionalClassification,
    RigorMetrics,
)

logger = structlog.get_logger(__name__)

# Pesos del score global
_W_IPP = Decimal("0.50")
_W_ITP = Decimal("0.30")
_W_ITR = Decimal("0.20")

# Penalización por día de retraso
_DELAY_PENALTY_APPROVAL    = Decimal("0.5")   # puntos / día
_DELAY_PENALTY_PUBLICATION = Decimal("1.0")   # puntos / día

# Días de retraso en una prórroga (ejercicio completo sin presupuesto)
_PRORROGA_DELAY_DAYS = 365


def _d(v) -> Decimal:
    """Convierte a Decimal de forma segura."""
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round4(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class RigorMetricsService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_and_store(self, fiscal_year: int) -> Optional[RigorMetrics]:
        """
        Calcula todas las métricas para el ejercicio y las persiste.
        Retorna el objeto RigorMetrics creado.
        """
        # Obtener FiscalYear
        fy_result = await self.db.execute(
            select(FiscalYear).where(FiscalYear.year == fiscal_year)
        )
        fy = fy_result.scalar_one_or_none()
        if not fy:
            logger.warning("fiscal_year_not_found", year=fiscal_year)
            return None

        # Snapshot más reciente de ejecución de gastos
        snap_result = await self.db.execute(
            select(BudgetSnapshot)
            .where(BudgetSnapshot.fiscal_year_id == fy.id)
            .where(BudgetSnapshot.phase == "executed_expense")
            .order_by(BudgetSnapshot.snapshot_date.desc())
            .limit(1)
        )
        snapshot = snap_result.scalar_one_or_none()
        if not snapshot:
            logger.warning("no_snapshot_for_metrics", year=fiscal_year)
            return None

        # ── A) Ejecución de gastos por capítulo ──────────────────────────────
        chapter_rows = await self.db.execute(
            select(
                func.substr(EconomicClassification.chapter, 1, 1).label("chapter"),
                func.sum(BudgetLine.initial_credits).label("initial"),
                func.sum(BudgetLine.final_credits).label("final"),
                func.sum(BudgetLine.recognized_obligations).label("obligations"),
                func.sum(BudgetLine.modifications).label("modifications"),
            )
            .join(BudgetLine.economic)
            .where(BudgetLine.snapshot_id == snapshot.id)
            .where(EconomicClassification.direction == "expense")
            .group_by("chapter")
            .order_by("chapter")
        )
        chapters = chapter_rows.all()

        total_initial    = sum(_d(r.initial)       for r in chapters)
        total_final      = sum(_d(r.final)         for r in chapters)
        total_obligations = sum(_d(r.obligations)  for r in chapters)
        total_mods       = sum(_d(r.modifications) for r in chapters)

        # ── B) Ejecución de ingresos ──────────────────────────────────────────
        # Los ingresos están en snapshots de phase=executed_revenue (fichero aparte)
        rev_snap_result = await self.db.execute(
            select(BudgetSnapshot)
            .where(BudgetSnapshot.fiscal_year_id == fy.id)
            .where(BudgetSnapshot.phase == "executed_revenue")
            .order_by(BudgetSnapshot.snapshot_date.desc())
            .limit(1)
        )
        rev_snapshot = rev_snap_result.scalar_one_or_none()

        if rev_snapshot:
            # final_forecast puede ser NULL en XLS más antiguos; reconstruir como ini + mods
            _eff_final_fc = func.coalesce(
                BudgetLine.final_forecast,
                BudgetLine.initial_forecast + func.coalesce(BudgetLine.modifications, 0),
            )
            rev_result = await self.db.execute(
                select(
                    func.sum(_eff_final_fc).label("final_fc"),
                    func.sum(BudgetLine.recognized_rights).label("rights"),
                )
                .join(BudgetLine.economic)
                .where(BudgetLine.snapshot_id == rev_snapshot.id)
                .where(EconomicClassification.direction == "revenue")
            )
            rev = rev_result.one()
            total_final_fc = _d(rev.final_fc)
            total_rights   = _d(rev.rights)
        else:
            total_final_fc = Decimal("0")
            total_rights   = Decimal("0")

        # ── C) Modificaciones ─────────────────────────────────────────────────
        mods_result = await self.db.execute(
            select(func.count(BudgetModification.id))
            .where(BudgetModification.fiscal_year_id == fy.id)
            .where(BudgetModification.status == "approved")
        )
        num_mods = mods_result.scalar() or 0

        # ── D) Tasas globales ─────────────────────────────────────────────────
        expense_exec_rate = (
            _round4(total_obligations / total_final)
            if total_final > 0 else Decimal("0")
        )
        revenue_exec_rate = (
            _round4(total_rights / total_final_fc)
            if total_final_fc > 0 else Decimal("0")
        )
        modification_rate = (
            _round4(total_mods / total_initial)
            if total_initial > 0 else Decimal("0")
        )

        # ── E) Índice de Precisión (IPP) ──────────────────────────────────────
        # Ponderado por capítulo: cada capítulo contribuye según su peso
        # en el total de créditos definitivos
        ipp = Decimal("0")
        if total_final > 0:
            for row in chapters:
                ch_final = _d(row.final)
                ch_obligations = _d(row.obligations)
                if ch_final <= 0:
                    continue
                ch_rate = ch_obligations / ch_final
                ch_ipp = Decimal("100") * (Decimal("1") - abs(Decimal("1") - ch_rate))
                ch_weight = ch_final / total_final
                ipp += ch_ipp * ch_weight
        ipp = max(Decimal("0"), _round2(ipp))

        # ── F) Índice de Puntualidad (ITP) ────────────────────────────────────
        if fy.is_extension:
            # Prórroga = el Ayuntamiento no aprobó ppto antes del ejercicio
            approval_delay = _PRORROGA_DELAY_DAYS
            itp = Decimal("0")
        elif fy.approval_delay_days is not None:
            approval_delay = max(0, fy.approval_delay_days)
            itp = max(
                Decimal("0"),
                Decimal("100") - Decimal(str(approval_delay)) * _DELAY_PENALTY_APPROVAL
            )
        else:
            # Sin fecha de aprobación conocida
            approval_delay = None
            itp = Decimal("0")

        itp = _round2(itp)

        # ── G) Índice de Transparencia (ITR) ──────────────────────────────────
        if fy.publication_delay_days is not None:
            pub_delay = max(0, fy.publication_delay_days)
            itr = max(
                Decimal("0"),
                Decimal("100") - Decimal(str(pub_delay)) * _DELAY_PENALTY_PUBLICATION
            )
        else:
            pub_delay = None
            itr = Decimal("50")   # dato desconocido → penalización media

        itr = _round2(itr)

        # ── H) Score Global ───────────────────────────────────────────────────
        global_score = _round2(ipp * _W_IPP + itp * _W_ITP + itr * _W_ITR)

        # ── I) Desglose por capítulo (JSONB) ──────────────────────────────────
        by_chapter = {}
        for row in chapters:
            ch = row.chapter
            ch_final = _d(row.final)
            ch_obligations = _d(row.obligations)
            exec_rate = float(ch_obligations / ch_final) if ch_final > 0 else 0
            mod_rate = float(_d(row.modifications) / _d(row.initial)) if _d(row.initial) > 0 else 0
            by_chapter[ch] = {
                "initial":          float(_d(row.initial)),
                "final":            float(ch_final),
                "obligations":      float(ch_obligations),
                "execution_rate":   round(exec_rate, 4),
                "modification_rate": round(mod_rate, 4),
                "ipp":              round(max(0, 100 * (1 - abs(1 - exec_rate))), 2),
            }

        # ── J) Desglose por programa (JSONB, top 20) ──────────────────────────
        prog_rows = await self.db.execute(
            select(
                FunctionalClassification.program.label("program"),
                FunctionalClassification.description.label("prog_desc"),
                func.sum(BudgetLine.final_credits).label("final"),
                func.sum(BudgetLine.recognized_obligations).label("obligations"),
            )
            .join(BudgetLine.functional)
            .where(BudgetLine.snapshot_id == snapshot.id)
            .where(BudgetLine.final_credits > 0)
            .group_by(
                FunctionalClassification.program,
                FunctionalClassification.description,
            )
            .order_by(func.sum(BudgetLine.final_credits).desc())
            .limit(20)
        )
        by_program = {}
        for row in prog_rows.all():
            if not row.program:
                continue
            pf = _d(row.final)
            po = _d(row.obligations)
            by_program[row.program] = {
                "description":   row.prog_desc or f"Programa {row.program}",
                "final":         float(pf),
                "obligations":   float(po),
                "execution_rate": round(float(po / pf), 4) if pf > 0 else 0,
            }

        # ── K) Persistir ──────────────────────────────────────────────────────
        # Borrar métricas anteriores del ejercicio para evitar duplicados
        await self.db.execute(
            delete(RigorMetrics).where(RigorMetrics.fiscal_year_id == fy.id)
        )

        metrics = RigorMetrics(
            fiscal_year_id=fy.id,
            snapshot_id=snapshot.id,
            expense_execution_rate=expense_exec_rate,
            revenue_execution_rate=revenue_exec_rate,
            modification_rate=modification_rate,
            num_modifications=num_mods,
            approval_delay_days=approval_delay,
            publication_delay_days=fy.publication_delay_days,
            precision_index=ipp,
            timeliness_index=itp,
            transparency_index=itr,
            global_rigor_score=global_score,
            by_chapter=by_chapter,
            by_program=by_program,
        )
        self.db.add(metrics)
        await self.db.flush()

        logger.info(
            "metrics_computed",
            year=fiscal_year,
            ipp=float(ipp),
            itp=float(itp),
            itr=float(itr),
            score=float(global_score),
            expense_exec=float(expense_exec_rate),
        )
        return metrics

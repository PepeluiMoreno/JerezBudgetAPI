"""
Servicio de reconciliación de modificaciones presupuestarias.

Compara:
  A) La suma de la columna `modifications` del XLSX de ejecución más reciente
     (la "verdad contable" del sistema)
  B) La suma de los importes introducidos manualmente en BudgetModification
     (lo que conocemos de los expedientes individuales)

El delta A - B indica cuánto queda sin registrar.
Si delta = 0 → cuadre perfecto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.budget import (
    BudgetLine,
    BudgetModification,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
)

logger = structlog.get_logger(__name__)

MOD_TYPE_LABELS = {
    "transfer":       "Transferencia de crédito",
    "generate":       "Generación de crédito",
    "carry_forward":  "Incorporación de remanentes",
    "supplementary":  "Suplemento de crédito",
    "credit_reduction": "Minoración de crédito",
}


@dataclass
class ChapterReconciliation:
    chapter: str
    chapter_name: str
    xlsx_modifications: Decimal       # suma columna modifications del XLSX
    entered_modifications: Decimal    # suma de expedientes introducidos
    delta: Decimal                    # xlsx - entered  (0 = cuadre)

    @property
    def is_balanced(self) -> bool:
        return abs(self.delta) < Decimal("0.01")

    @property
    def delta_pct(self) -> Optional[float]:
        if self.xlsx_modifications and self.xlsx_modifications != 0:
            return float(self.delta / self.xlsx_modifications * 100)
        return None


@dataclass
class ReconciliationResult:
    fiscal_year: int
    snapshot_date: Optional[str]

    # Totales globales
    xlsx_total_modifications: Decimal = Decimal("0")
    entered_total_modifications: Decimal = Decimal("0")

    # Desglose por capítulo
    by_chapter: list[ChapterReconciliation] = field(default_factory=list)

    # Expedientes
    num_modifications_entered: int = 0
    num_modifications_approved: int = 0
    num_modifications_in_progress: int = 0

    @property
    def global_delta(self) -> Decimal:
        return self.xlsx_total_modifications - self.entered_total_modifications

    @property
    def is_balanced(self) -> bool:
        return abs(self.global_delta) < Decimal("0.01")

    @property
    def balance_pct(self) -> Optional[float]:
        """Porcentaje del total del XLSX que está reconciliado."""
        if self.xlsx_total_modifications and self.xlsx_total_modifications != 0:
            return float(self.entered_total_modifications / self.xlsx_total_modifications * 100)
        return None


CHAPTER_NAMES = {
    "1": "Personal",
    "2": "Bienes corrientes y servicios",
    "3": "Gastos financieros",
    "4": "Transferencias corrientes",
    "5": "Fondo de contingencia",
    "6": "Inversiones reales",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}


async def get_latest_snapshot(db: AsyncSession, fiscal_year: int) -> Optional[BudgetSnapshot]:
    result = await db.execute(
        select(BudgetSnapshot)
        .join(FiscalYear)
        .where(FiscalYear.year == fiscal_year)
        .where(BudgetSnapshot.phase == "executed")
        .order_by(BudgetSnapshot.snapshot_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_reconciliation(
    db: AsyncSession,
    fiscal_year: int,
) -> ReconciliationResult:
    """
    Calcula el estado de reconciliación para un ejercicio.
    """
    result = ReconciliationResult(fiscal_year=fiscal_year, snapshot_date=None)

    # ── A) Totales del XLSX por capítulo ─────────────────────────────────────
    snapshot = await get_latest_snapshot(db, fiscal_year)

    if snapshot:
        result.snapshot_date = snapshot.snapshot_date.strftime("%d/%m/%Y")

        xlsx_rows = await db.execute(
            select(
                func.substr(EconomicClassification.chapter, 1, 1).label("chapter"),
                func.sum(BudgetLine.modifications).label("xlsx_mods"),
            )
            .join(BudgetLine.economic)
            .where(BudgetLine.snapshot_id == snapshot.id)
            .where(EconomicClassification.direction == "expense")
            .where(BudgetLine.modifications.isnot(None))
            .group_by("chapter")
            .order_by("chapter")
        )
        xlsx_by_chapter: dict[str, Decimal] = {
            row.chapter: row.xlsx_mods or Decimal("0")
            for row in xlsx_rows.all()
        }
        result.xlsx_total_modifications = sum(xlsx_by_chapter.values(), Decimal("0"))

    # ── B) Totales introducidos manualmente por tipo ──────────────────────────
    mod_rows = await db.execute(
        select(BudgetModification)
        .join(FiscalYear)
        .where(FiscalYear.year == fiscal_year)
        .order_by(BudgetModification.ref)
    )
    modifications = mod_rows.scalars().all()

    result.num_modifications_entered = len(modifications)
    result.num_modifications_approved = sum(1 for m in modifications if m.status == "approved")
    result.num_modifications_in_progress = sum(1 for m in modifications if m.status == "in_progress")

    entered_total = sum(
        (m.total_amount or Decimal("0")) for m in modifications if m.status == "approved"
    )
    result.entered_total_modifications = entered_total

    # ── C) Desglose por capítulo ──────────────────────────────────────────────
    # (las modificaciones manuales no siempre tienen capítulo — se muestra como global)
    if snapshot:
        for chapter, xlsx_amount in sorted(xlsx_by_chapter.items()):
            if xlsx_amount == 0:
                continue
            result.by_chapter.append(ChapterReconciliation(
                chapter=chapter,
                chapter_name=CHAPTER_NAMES.get(chapter, f"Capítulo {chapter}"),
                xlsx_modifications=xlsx_amount,
                entered_modifications=Decimal("0"),  # sin desglose por cap. en PDFs
                delta=xlsx_amount,
            ))

        # Si el total cuadra, marcamos todos los capítulos como reconciliados
        if result.is_balanced:
            for ch in result.by_chapter:
                ch.entered_modifications = ch.xlsx_modifications
                ch.delta = Decimal("0")

    logger.info(
        "reconciliation_computed",
        year=fiscal_year,
        xlsx_total=float(result.xlsx_total_modifications),
        entered_total=float(result.entered_total_modifications),
        delta=float(result.global_delta),
        balanced=result.is_balanced,
    )
    return result

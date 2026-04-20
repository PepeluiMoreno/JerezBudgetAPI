"""
Modelos ORM — CityDashboard
Representan el esquema presupuestario del municipio propio (ciudad home).

Convención de nomenclatura:
  - Tablas en snake_case plural
  - FKs siempre con índice explícito
  - Importes en Numeric(16,2) — sin floats para evitar errores de redondeo
  - JSONB para desgloses por capítulo/programa (evita joins costosos en dashboard)
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── 1. AÑOS FISCALES ─────────────────────────────────────────────────────────

class FiscalYear(Base):
    """
    Representa un ejercicio presupuestario.
    is_extension=True cuando el ayuntamiento prorroga el presupuesto anterior
    (caso 2026 = prórroga de 2025).
    """
    __tablename__ = "fiscal_years"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)

    # Prórroga
    is_extension: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extended_from_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Estado: draft | approved | extended | closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    # Fechas clave para índices de puntualidad
    initial_budget_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True,
        comment="Fecha de aprobación del presupuesto (o extensión)")
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True,
        comment="Fecha de primera publicación en portal de transparencia")
    stability_report_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True,
        comment="Fecha informe de estabilidad presupuestaria")

    # Metadatos
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now())

    # ── Relaciones ──────────────────────────────────────────────
    snapshots: Mapped[list[BudgetSnapshot]] = relationship(
        back_populates="fiscal_year", cascade="all, delete-orphan"
    )
    modifications: Mapped[list[BudgetModification]] = relationship(
        back_populates="fiscal_year", cascade="all, delete-orphan"
    )
    rigor_metrics: Mapped[list[RigorMetrics]] = relationship(
        back_populates="fiscal_year", cascade="all, delete-orphan"
    )

    # ── Propiedades calculadas ───────────────────────────────────
    @property
    def approval_delay_days(self) -> Optional[int]:
        """Días desde el 1 de enero hasta la aprobación. Negativo = aprobado antes."""
        if self.initial_budget_date:
            jan1 = date(self.year, 1, 1)
            return (self.initial_budget_date - jan1).days
        return None  # No aprobado todavía

    @property
    def publication_delay_days(self) -> Optional[int]:
        """Días entre aprobación y publicación en transparencia."""
        if self.initial_budget_date and self.publication_date:
            return (self.publication_date - self.initial_budget_date).days
        return None

    def __repr__(self) -> str:
        ext = " (prórroga)" if self.is_extension else ""
        return f"<FiscalYear {self.year}{ext} [{self.status}]>"


# ── 2. CLASIFICACIONES ────────────────────────────────────────────────────────

class EconomicClassification(Base):
    """
    Clasificación económica del presupuesto español.
    Jerárquica: capítulo (1 dígito) → artículo (2) → concepto (5) → subconcepto (8+)
    """
    __tablename__ = "economic_classifications"
    __table_args__ = (
        CheckConstraint("direction IN ('expense', 'revenue')", name="ck_direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)

    # Niveles jerárquicos
    chapter: Mapped[str] = mapped_column(String(2), nullable=False, index=True,
        comment="Capítulo: 1-9 gastos, A-E ingresos")
    article: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    concept: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    subconcept: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False,
        comment="expense | revenue")

    # Relación
    budget_lines: Mapped[list[BudgetLine]] = relationship(back_populates="economic")

    def __repr__(self) -> str:
        return f"<EconomicClass {self.code} [{self.direction}]>"


class FunctionalClassification(Base):
    """
    Clasificación funcional / por programas.
    Área → Política → Grupo de programa → Programa → Subprograma
    """
    __tablename__ = "functional_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)

    area: Mapped[Optional[str]] = mapped_column(String(1), nullable=True,
        comment="1 dígito — área de gasto")
    policy: Mapped[Optional[str]] = mapped_column(String(2), nullable=True,
        comment="2 dígitos — política de gasto")
    program_group: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    program: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    subprogram: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    budget_lines: Mapped[list[BudgetLine]] = relationship(back_populates="functional")

    def __repr__(self) -> str:
        return f"<FunctionalClass {self.code}>"


class OrganicClassification(Base):
    """
    Clasificación orgánica (quién gasta).
    Sección → Servicio
    """
    __tablename__ = "organic_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)

    section: Mapped[Optional[str]] = mapped_column(String(2), nullable=True,
        comment="Sección — gran área orgánica")
    service: Mapped[Optional[str]] = mapped_column(String(4), nullable=True,
        comment="Servicio — unidad gestora")

    description: Mapped[str] = mapped_column(Text, nullable=False)

    budget_lines: Mapped[list[BudgetLine]] = relationship(back_populates="organic")

    def __repr__(self) -> str:
        return f"<OrganicClass {self.code}>"


# ── 3. SNAPSHOTS DE EJECUCIÓN ────────────────────────────────────────────────

class BudgetSnapshot(Base):
    """
    Fotografía de la ejecución presupuestaria en una fecha concreta.
    Cada vez que el Ayuntamiento publica un nuevo XLSX se crea un snapshot.
    """
    __tablename__ = "budget_snapshots"
    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "snapshot_date", "phase",
                         name="uq_snapshot_year_date_phase"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(
        ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False,
        comment="Fecha de corte del XLSX (ej: 23/03/2026)")
    # initial = presupuesto inicial; executed = ejecución parcial/final
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="executed")

    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
        comment="URL de descarga del XLSX original")
    source_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True,
        comment="Hash SHA-256 del fichero para deduplicación")
    minio_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
        comment="Ruta en MinIO: bucket/year/filename")

    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        server_default=func.now())

    # Relaciones
    fiscal_year: Mapped[FiscalYear] = relationship(back_populates="snapshots")
    budget_lines: Mapped[list[BudgetLine]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BudgetSnapshot {self.snapshot_date} [{self.phase}]>"


# ── 4. LÍNEAS PRESUPUESTARIAS ─────────────────────────────────────────────────

class BudgetLine(Base):
    """
    Línea presupuestaria individual (aplicación presupuestaria).
    Cada línea combina las tres clasificaciones y contiene los importes
    en todas las fases del ciclo presupuestario.

    Una misma aplicación (organic+functional+economic) aparece en múltiples
    snapshots para poder trazar la evolución temporal.
    """
    __tablename__ = "budget_lines"
    __table_args__ = (
        Index("ix_bl_snapshot_economic", "snapshot_id", "economic_id"),
        Index("ix_bl_snapshot_functional", "snapshot_id", "functional_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("budget_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organic_classifications.id"), nullable=True
    )
    functional_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("functional_classifications.id"), nullable=True
    )
    economic_id: Mapped[int] = mapped_column(
        ForeignKey("economic_classifications.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Gastos ──────────────────────────────────────────────────
    initial_credits: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Créditos iniciales (presupuesto aprobado)")
    modifications: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Suma de modificaciones presupuestarias")
    final_credits: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Créditos definitivos = iniciales + modificaciones")
    commitments: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Autorizaciones y Disposiciones (A/D)")
    recognized_obligations: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Obligaciones reconocidas — gasto devengado")
    payments_made: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Pagos realizados — gasto efectivamente pagado")
    pending_payment: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Pendiente de pago = obligaciones - pagos")

    # ── Ingresos ─────────────────────────────────────────────────
    initial_forecast: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Previsiones iniciales de ingreso")
    final_forecast: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Previsiones definitivas = iniciales + modificaciones")
    recognized_rights: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Derechos reconocidos netos")
    net_collection: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Recaudación neta")
    pending_collection: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2),
        comment="Pendiente de cobro = derechos - recaudación")

    # ── Relaciones ───────────────────────────────────────────────
    snapshot: Mapped[BudgetSnapshot] = relationship(back_populates="budget_lines")
    organic: Mapped[Optional[OrganicClassification]] = relationship(back_populates="budget_lines")
    functional: Mapped[Optional[FunctionalClassification]] = relationship(back_populates="budget_lines")
    economic: Mapped[EconomicClassification] = relationship(back_populates="budget_lines")

    # ── Propiedades calculadas ───────────────────────────────────
    @property
    def execution_rate(self) -> Optional[float]:
        """Tasa de ejecución de gastos: obligaciones / créditos definitivos."""
        if self.final_credits and self.final_credits > 0 and self.recognized_obligations is not None:
            return float(self.recognized_obligations / self.final_credits)
        return None

    @property
    def revenue_execution_rate(self) -> Optional[float]:
        """Tasa de ejecución de ingresos: derechos / previsiones definitivas."""
        if self.final_forecast and self.final_forecast > 0 and self.recognized_rights is not None:
            return float(self.recognized_rights / self.final_forecast)
        return None

    @property
    def deviation_amount(self) -> Optional[Decimal]:
        """Desviación absoluta en gastos: créditos definitivos - obligaciones."""
        if self.final_credits is not None and self.recognized_obligations is not None:
            return self.final_credits - self.recognized_obligations
        return None

    @property
    def modification_rate(self) -> Optional[float]:
        """Tasa de modificación: (definitivos - iniciales) / iniciales."""
        if self.initial_credits and self.initial_credits > 0 and self.final_credits is not None:
            return float((self.final_credits - self.initial_credits) / self.initial_credits)
        return None

    def __repr__(self) -> str:
        return f"<BudgetLine eco={self.economic_id} snap={self.snapshot_id}>"


# ── 5. MODIFICACIONES PRESUPUESTARIAS ────────────────────────────────────────

class BudgetModification(Base):
    """
    Expediente de modificación presupuestaria (T001/2026, T002/2026, ...).
    Tipos: transfer (transferencia de crédito), generate (generación de crédito),
           carry_forward (incorporación de remanentes).
    """
    __tablename__ = "budget_modifications"
    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "ref", name="uq_modification_ref"),
        CheckConstraint(
            "mod_type IN ('transfer', 'generate', 'carry_forward', 'supplementary', 'credit_reduction')",
            name="ck_mod_type"
        ),
        CheckConstraint(
            "status IN ('approved', 'in_progress', 'rejected')",
            name="ck_mod_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(
        ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ref: Mapped[str] = mapped_column(String(20), nullable=False,
        comment="Referencia del expediente: T003/2026")
    mod_type: Mapped[str] = mapped_column(String(30), nullable=False,
        comment="transfer | generate | carry_forward | supplementary | credit_reduction")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")

    resolution_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        server_default=func.now())

    # Relación
    fiscal_year: Mapped[FiscalYear] = relationship(back_populates="modifications")

    def __repr__(self) -> str:
        return f"<BudgetModification {self.ref} [{self.mod_type}]>"


# ── 6. MÉTRICAS DE RIGOR ─────────────────────────────────────────────────────

class RigorMetrics(Base):
    """
    Métricas precalculadas de rigor presupuestario por ejercicio y snapshot.
    Se recalculan cada vez que se ingiere un nuevo snapshot.
    El snapshot_id puede ser NULL para métricas anuales de cierre.
    """
    __tablename__ = "rigor_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(
        ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("budget_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        server_default=func.now())

    # ── Tasas globales ───────────────────────────────────────────
    expense_execution_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    revenue_execution_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    modification_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    num_modifications: Mapped[int] = mapped_column(Integer, default=0)

    # ── Puntualidad ──────────────────────────────────────────────
    approval_delay_days: Mapped[Optional[int]] = mapped_column(Integer,
        comment="Días desde 1-ene hasta aprobación. Nulo si no aprobado.")
    publication_delay_days: Mapped[Optional[int]] = mapped_column(Integer,
        comment="Días entre aprobación y publicación en transparencia.")

    # ── Scores normalizados 0-100 ─────────────────────────────────
    precision_index: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2),
        comment="Índice Precisión Presupuestaria (IPP)")
    timeliness_index: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2),
        comment="Índice de Puntualidad (ITP)")
    transparency_index: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2),
        comment="Índice de Transparencia (ITR)")
    global_rigor_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2),
        comment="Score Global de Rigor = IPP×0.5 + ITP×0.3 + ITR×0.2")

    # ── Desgloses JSONB ──────────────────────────────────────────
    by_chapter: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True,
        comment="Métricas desglosadas por capítulo económico")
    by_program: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True,
        comment="Métricas desglosadas por programa funcional")
    by_section: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True,
        comment="Métricas desglosadas por sección orgánica")

    # Relaciones
    fiscal_year: Mapped[FiscalYear] = relationship(back_populates="rigor_metrics")

    def __repr__(self) -> str:
        score = f"{self.global_rigor_score:.1f}" if self.global_rigor_score else "N/A"
        return f"<RigorMetrics year={self.fiscal_year_id} score={score}>"


# ── 7. ENTIDADES MUNICIPALES ─────────────────────────────────────────────────

class MunicipalEntity(Base):
    """
    Catálogo de entidades que forman la corporación municipal de una ciudad.

    Incluye el ayuntamiento, organismos autónomos, empresas municipales,
    fundaciones, consorcios y el registro consolidado del grupo.

    Diseño genérico: no hay nombres de empresa hardcodeados. La tabla se puebla
    por municipio (ine_code) vía seed_entities.py desde rendiciondecuentas.es.

    alias_fuentes almacena el texto exacto con el que cada fuente de datos externa
    (PDFs de PMP, CESEL XLSX…) identifica a esta entidad, permitiendo la resolución
    nombre→NIF sin lógica específica por ciudad.
    """
    __tablename__ = "municipal_entities"
    __table_args__ = (
        Index("ix_municipal_entities_ine_code", "ine_code"),
        Index("ix_municipal_entities_parent_nif", "parent_nif"),
    )

    nif: Mapped[str] = mapped_column(String(20), primary_key=True,
        comment="NIF fiscal real (P..., Q...) o sintético G{ine_code}0 para grupo consolidado")
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    nombre_corto: Mapped[str] = mapped_column(String(60), nullable=False,
        comment="Siglas o nombre abreviado para uso en UI")
    tipo: Mapped[str] = mapped_column(String(20), nullable=False,
        comment="ayto | opa | empresa | fundacion | consorcio | grupo")
    parent_nif: Mapped[Optional[str]] = mapped_column(String(20),
        ForeignKey("municipal_entities.nif", ondelete="SET NULL"), nullable=True,
        comment="NIF del ayuntamiento cabecera al que pertenece esta entidad")
    ine_code: Mapped[str] = mapped_column(String(10), nullable=False,
        comment="Código INE del municipio (5 dígitos, ej: 11020)")
    id_rendicion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
        comment="ID de la entidad en rendiciondecuentas.es — permite scraper CG automático")
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False,
        comment="False = entidad disuelta; se conserva el histórico")
    alias_fuentes: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
        comment=(
            'JSON: {"pmp_pdf": "texto en el PDF", "cesel": "nombre en XLSX", …} '
            "— mapea el texto literal de cada fuente al NIF de esta entidad"
        ))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def alias(self, fuente: str) -> Optional[str]:
        """Devuelve el nombre de esta entidad en la fuente indicada, o None."""
        import json
        if not self.alias_fuentes:
            return None
        try:
            return json.loads(self.alias_fuentes).get(fuente)
        except (ValueError, TypeError):
            return None

    def __repr__(self) -> str:
        return f"<MunicipalEntity {self.nif} {self.nombre_corto} ({self.tipo})>"

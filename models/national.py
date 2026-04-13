"""
Modelos ORM — Capa 2: Comparativa Nacional
Representa los datos del Ministerio de Hacienda (CONPREL)
para todos los municipios españoles.

Convenciones:
  - Código INE: 5 dígitos, string (ej: '11020' para Jerez)
  - Capítulo económico: 1 dígito string ('1'-'9')
  - Área funcional: 1 dígito string ('1'-'9')
  - data_type: 'budget' (presupuesto inicial) | 'liquidation' (liquidación)
  - Importes en Numeric(16,2) — sin floats
  - Per-cápita en Numeric(10,2) — 2 decimales suficientes
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey,
    Index, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from models.budget import Base  # compartimos la misma Base declarativa


# ── 1. MUNICIPIOS ─────────────────────────────────────────────────────────────

class Municipality(Base):
    """
    Catálogo de municipios españoles.
    Fuente: INE — Relación de Municipios y sus Códigos por Provincias.
    El código INE de 5 dígitos es la clave de integración con CONPREL.
    Jerez de la Frontera: ine_code = '11020'
    """
    __tablename__ = "municipalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identificador INE — 5 dígitos (2 provincia + 3 municipio)
    ine_code: Mapped[str] = mapped_column(
        String(5), unique=True, nullable=False, index=True,
        comment="Código INE 5 dígitos: '11020' = Jerez de la Frontera"
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Provincia
    province_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    province_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Comunidad Autónoma
    ccaa_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    ccaa_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Población más reciente (desnormalizado para consultas rápidas)
    population: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    population_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadatos
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    population_history: Mapped[list[MunicipalPopulation]] = relationship(
        back_populates="municipality", cascade="all, delete-orphan"
    )
    budgets: Mapped[list[MunicipalBudget]] = relationship(
        back_populates="municipality", cascade="all, delete-orphan"
    )
    peer_memberships: Mapped[list[PeerGroupMember]] = relationship(
        back_populates="municipality"
    )

    @property
    def is_jerez(self) -> bool:
        return self.ine_code == "11020"

    def __repr__(self) -> str:
        return f"<Municipality {self.ine_code} {self.name}>"


# ── 2. SERIE DE POBLACIÓN ─────────────────────────────────────────────────────

class MunicipalPopulation(Base):
    """
    Serie histórica de población por municipio y año.
    Fuente: INE Padrón Municipal de Habitantes.
    Necesaria para calcular importes per cápita.
    """
    __tablename__ = "municipal_population"
    __table_args__ = (
        UniqueConstraint("municipality_id", "year", name="uq_mun_pop_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(
        ForeignKey("municipalities.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INE_PADRON"
    )

    municipality: Mapped[Municipality] = relationship(back_populates="population_history")

    def __repr__(self) -> str:
        return f"<MunicipalPopulation {self.municipality_id} {self.year}={self.population}>"


# ── 3. PRESUPUESTO ANUAL MUNICIPAL ────────────────────────────────────────────

class MunicipalBudget(Base):
    """
    Cabecera presupuestaria anual de un municipio.
    Una fila por (municipio, año, tipo_dato).
    tipo_dato: 'budget' = presupuesto aprobado inicial
               'liquidation' = liquidación definitiva

    Contiene totales agregados para consultas rápidas de ranking.
    El detalle por capítulo está en MunicipalBudgetChapter.
    """
    __tablename__ = "municipal_budgets"
    __table_args__ = (
        UniqueConstraint(
            "municipality_id", "fiscal_year", "data_type",
            name="uq_mun_budget_year_type"
        ),
        CheckConstraint(
            "data_type IN ('budget', 'liquidation')",
            name="ck_mun_budget_data_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(
        ForeignKey("municipalities.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    data_type: Mapped[str] = mapped_column(
        String(15), nullable=False,
        comment="budget | liquidation"
    )

    # Metadatos de la publicación
    source_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
        comment="Fecha de publicación por el Ministerio de Hacienda"
    )
    conprel_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Año del fichero MDB del que proviene"
    )
    is_extension: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True si el presupuesto es una prórroga"
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Totales desnormalizados (para ranking rápido) ────────────────────────
    # Gastos
    total_expense_initial: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Total créditos iniciales gastos"
    )
    total_expense_final: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Total créditos definitivos gastos"
    )
    total_expense_executed: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Total obligaciones reconocidas"
    )
    # Ingresos
    total_revenue_initial: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Total previsiones iniciales ingresos"
    )
    total_revenue_executed: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Total derechos reconocidos netos"
    )

    # ── Per-cápita (desnormalizado para velocidad) ───────────────────────────
    expense_executed_per_capita: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), comment="Gasto ejecutado / población"
    )
    revenue_executed_per_capita: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), comment="Ingreso ejecutado / población"
    )

    # ── Tasas precalculadas ───────────────────────────────────────────────────
    expense_execution_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), comment="obligaciones / créditos definitivos"
    )
    revenue_execution_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), comment="derechos / previsiones definitivas"
    )
    modification_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4),
        comment="(créditos definitivos - iniciales) / iniciales"
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relaciones
    municipality: Mapped[Municipality] = relationship(back_populates="budgets")
    chapters: Mapped[list[MunicipalBudgetChapter]] = relationship(
        back_populates="municipal_budget", cascade="all, delete-orphan"
    )
    programs: Mapped[list[MunicipalBudgetProgram]] = relationship(
        back_populates="municipal_budget", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<MunicipalBudget {self.municipality_id} "
            f"{self.fiscal_year} [{self.data_type}]>"
        )


# ── 4. CAPÍTULOS ECONÓMICOS ───────────────────────────────────────────────────

class MunicipalBudgetChapter(Base):
    """
    Detalle por capítulo económico de un presupuesto municipal anual.
    Es la granularidad principal para la comparativa entre ciudades.
    Un presupuesto tiene hasta 9 capítulos de gastos + 9 de ingresos.
    """
    __tablename__ = "municipal_budget_chapters"
    __table_args__ = (
        Index(
            "ix_mbc_budget_chapter_dir",
            "municipal_budget_id", "chapter", "direction"
        ),
        UniqueConstraint(
            "municipal_budget_id", "chapter", "direction",
            name="uq_mbc_chapter_dir"
        ),
        CheckConstraint(
            "direction IN ('expense', 'revenue')",
            name="ck_mbc_direction"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipal_budget_id: Mapped[int] = mapped_column(
        ForeignKey("municipal_budgets.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    chapter: Mapped[str] = mapped_column(
        String(1), nullable=False,
        comment="Capítulo económico: '1'-'9'"
    )
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="expense | revenue"
    )

    # Importes
    initial_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Créditos iniciales (gastos) / Previsiones iniciales (ingresos)"
    )
    final_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Créditos definitivos / Previsiones definitivas"
    )
    executed_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(16, 2), comment="Obligaciones reconocidas (gastos) / Derechos reconocidos (ingresos)"
    )

    # Per-cápita (calculado durante ETL con población del año)
    initial_per_capita: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    executed_per_capita: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # Tasas
    execution_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), comment="executed / final (o initial si no hay final)"
    )
    modification_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), comment="(final - initial) / initial — solo gastos"
    )

    municipal_budget: Mapped[MunicipalBudget] = relationship(back_populates="chapters")

    def __repr__(self) -> str:
        return (
            f"<MunicipalBudgetChapter cap={self.chapter} "
            f"dir={self.direction} budget={self.municipal_budget_id}>"
        )


# ── 5. ÁREAS FUNCIONALES ─────────────────────────────────────────────────────

class MunicipalBudgetProgram(Base):
    """
    Detalle por área de gasto funcional (clasificación por programas).
    Nivel: área (1 dígito). Permite comparar "¿cuánto gasta cada municipio
    en seguridad, cultura, urbanismo, etc.?"

    Áreas ICAL:
      1 = Servicios públicos básicos
      2 = Actuaciones de protección y promoción social
      3 = Producción de bienes públicos de carácter preferente
      4 = Actuaciones de carácter económico
      9 = Actuaciones de carácter general
    """
    __tablename__ = "municipal_budget_programs"
    __table_args__ = (
        UniqueConstraint(
            "municipal_budget_id", "area_code",
            name="uq_mbp_budget_area"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipal_budget_id: Mapped[int] = mapped_column(
        ForeignKey("municipal_budgets.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    area_code: Mapped[str] = mapped_column(
        String(1), nullable=False,
        comment="Área funcional ICAL 1 dígito: '1'-'9'"
    )
    area_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    initial_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    executed_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    initial_per_capita: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    executed_per_capita: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    execution_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))

    municipal_budget: Mapped[MunicipalBudget] = relationship(back_populates="programs")


# ── 6. GRUPOS DE PARES ────────────────────────────────────────────────────────

class PeerGroup(Base):
    """
    Define un grupo de municipios para comparación contextualizada.
    Los criterios se almacenan como JSONB para flexibilidad.
    Ejemplos:
      - Municipios 100k-250k hab. en Andalucía
      - Municipios de la provincia de Cádiz
      - Capitales de provincia andaluzas
    """
    __tablename__ = "peer_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(
        String(60), unique=True, nullable=False,
        comment="Identificador URL-friendly: 'andalucia-100k-250k'"
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Criterios de pertenencia (para reconstruir el grupo tras nuevas ingestiones)
    criteria: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="{'pop_min': 100000, 'pop_max': 250000, 'ccaa_code': '01'}"
    )
    is_dynamic: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="True = recalcular miembros tras cada ingestión INE"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list[PeerGroupMember]] = relationship(
        back_populates="peer_group", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PeerGroup {self.slug}>"


class PeerGroupMember(Base):
    """Asocia municipios con grupos de pares."""
    __tablename__ = "peer_group_members"
    __table_args__ = (
        UniqueConstraint(
            "peer_group_id", "municipality_id",
            name="uq_pgm_group_mun"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    peer_group_id: Mapped[int] = mapped_column(
        ForeignKey("peer_groups.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    municipality_id: Mapped[int] = mapped_column(
        ForeignKey("municipalities.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    peer_group: Mapped[PeerGroup] = relationship(back_populates="members")
    municipality: Mapped[Municipality] = relationship(back_populates="peer_memberships")

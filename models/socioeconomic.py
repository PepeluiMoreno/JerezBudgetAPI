"""
Modelos ORM para datos socioeconómicos sincronizados desde OpenDataManager.

Solo se persisten localmente los datasets que CityDashboard necesita para JOINs SQL:
  - MunicipalPopulation  — padrón INE, necesario para calcular €/habitante
  - CuentaGeneralKpi     — KPIs de sostenibilidad extraídos de la Cuenta General XBRL

El resto de datos socioeconómicos (paro, renta, EOH, PMP) se consultan
directamente vía GraphQL en ODM (/graphql/data) sin necesidad de copia local.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.budget import Base


class InePadronMunicipal(Base):
    """
    Población municipal anual procedente del Padrón Municipal (INE) vía ODM.

    Cubre todos los municipios de España para poder calcular métricas per cápita
    tanto de Jerez como de su grupo de comparación (180k–250k hab.).
    A diferencia de models.national.MunicipalPopulation (datos CONPREL agregados),
    esta tabla almacena el desglose por sexo y usa código INE como clave.

    Fuente: ODM resource "INE - Padrón Municipal (todos los municipios)"
    Actualización: anual (junio), vía webhook ODM → POST /webhooks/odmgr
    """
    __tablename__ = "ine_padron_municipal"
    __table_args__ = (
        UniqueConstraint("municipio_cod", "year", "sexo_cod",
                         name="uq_ine_padron_municipio_year_sexo"),
        Index("ix_ine_padron_municipio_year", "municipio_cod", "year"),
        Index("ix_ine_padron_year", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipio_cod: Mapped[str] = mapped_column(String(10), nullable=False,
        comment="Código INE del municipio (5 dígitos, ej: 11020)")
    municipio_nombre: Mapped[Optional[str]] = mapped_column(String(200))
    year: Mapped[int] = mapped_column(Integer, nullable=False,
        comment="Año del padrón")
    sexo_cod: Mapped[str] = mapped_column(String(5), nullable=False, default="T",
        comment="Código de sexo: T=Total, H=Hombres, M=Mujeres")
    sexo_nombre: Mapped[Optional[str]] = mapped_column(String(20))
    habitantes: Mapped[Optional[int]] = mapped_column(Integer,
        comment="Población residente a 1 de enero")

    # Trazabilidad ODM
    odmgr_dataset_id: Mapped[Optional[str]] = mapped_column(String(36),
        comment="UUID del Dataset ODM que originó este registro")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<InePadronMunicipal {self.municipio_cod} {self.year} {self.sexo_cod}={self.habitantes}>"


class CuentaGeneralKpi(Base):
    """
    KPIs de sostenibilidad financiera extraídos de la Cuenta General XBRL.

    En lugar de persistir el detalle completo de cuentas XBRL (que puede ser
    muy voluminoso), se almacenan únicamente los KPIs calculados relevantes
    para el análisis de rigor: deuda viva, remanente de tesorería, ahorro neto, etc.

    Fuente: ODM resource "Cuenta General - Entidades Locales (XBRL)"
    Actualización: anual (julio), vía webhook ODM → POST /webhooks/odmgr
    """
    __tablename__ = "cuenta_general_kpis"
    __table_args__ = (
        UniqueConstraint("nif_entidad", "ejercicio", "kpi", "periodo",
                         name="uq_cgkpi_entidad_ejercicio_kpi_periodo"),
        Index("ix_cgkpi_ejercicio", "ejercicio"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nif_entidad: Mapped[str] = mapped_column(String(20), nullable=False,
        comment="NIF de la entidad local, ej: P1102900A")
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    kpi: Mapped[str] = mapped_column(String(80), nullable=False,
        comment=(
            "Código del KPI. Valores estándar: "
            "deuda_viva, remanente_tesoreria_gastos_generales, ahorro_neto, "
            "resultado_presupuestario_ajustado, activo_total, pasivo_total, "
            "ingresos_corrientes_liquidados, gastos_corrientes_liquidados"
        ))
    periodo: Mapped[str] = mapped_column(String(7), nullable=False, default="",
        server_default="",
        comment=(
            "Granularidad del dato. "
            "'' = anual (por defecto) | "
            "'01'-'12' = mensual (ej: '03' para marzo) | "
            "'T1'-'T4' = trimestral"
        ))
    valor: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2),
        comment="Valor en euros")
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="EUR")
    fuente_cuenta: Mapped[Optional[str]] = mapped_column(String(60),
        comment="Estado contable XBRL de origen: balance, liquidacion, tesoreria, resultado_economico")

    odmgr_dataset_id: Mapped[Optional[str]] = mapped_column(String(36))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<CuentaGeneralKpi {self.nif_entidad} {self.ejercicio} {self.kpi}={self.valor}>"


# ── Prioridad de fuentes (menor = más autoritativa) ──────────────────────────
SOURCE_PRIORITY: dict[str, int] = {
    "transparencia_ayto":    10,   # portal Ayuntamiento (directo, sin intermediario)
    "rendiciondecuentas_cg": 20,   # portal IGAE (validado externamente)
    "informe_cp":            30,   # Informe Control Permanente / Reglas Fiscales
    "calculado":             40,   # valores derivados por fórmula
}

def source_priority(fuente: str | None) -> int:
    """Devuelve la prioridad numérica de una fuente. Menor es más autoritativa."""
    if fuente is None:
        return 99
    for key, prio in SOURCE_PRIORITY.items():
        if key in (fuente or "").lower():
            return prio
    return 50  # fuente desconocida: prioridad media-baja


# ── Umbrales de alerta por KPI ────────────────────────────────────────────────

class KpiThreshold(Base):
    """
    Umbrales legales y de buena práctica para semáforos en el cuadro de mando.

    Cada fila define un nivel de alerta (verde/amarillo/rojo) para un KPI
    mediante un operador y un valor umbral. Se pueden definir múltiples umbrales
    por KPI (p.ej. amarillo a 30 días y rojo a 60 días para PMP).

    La base_legal documenta la norma que sustenta el umbral, haciendo el
    semáforo auditable y justificable ante interventores y auditores.
    """
    __tablename__ = "kpi_thresholds"
    __table_args__ = (
        UniqueConstraint("kpi", "nivel", "aplica_a", name="uq_threshold_kpi_nivel_aplica"),
        CheckConstraint("nivel IN ('verde', 'amarillo', 'rojo')", name="ck_threshold_nivel"),
        CheckConstraint("operador IN ('<', '>', '<=', '>=')", name="ck_threshold_operador"),
        CheckConstraint("aplica_a IN ('ayto', 'empresa', 'todos')", name="ck_threshold_aplica"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kpi: Mapped[str] = mapped_column(String(80), nullable=False,
        comment="kpi_code al que aplica este umbral")
    nivel: Mapped[str] = mapped_column(String(10), nullable=False,
        comment="'verde' | 'amarillo' | 'rojo'")
    operador: Mapped[str] = mapped_column(String(2), nullable=False,
        comment="Operador de comparación: '<' | '>' | '<=' | '>='")
    umbral: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False,
        comment="Valor límite del umbral")
    aplica_a: Mapped[str] = mapped_column(String(10), nullable=False, default="todos",
        comment="'ayto' (solo ayuntamiento) | 'empresa' | 'todos'")
    base_legal: Mapped[str] = mapped_column(String(200), nullable=False, default="",
        comment="Norma que sustenta el umbral, ej: 'Ley 15/2010 art.5'")
    descripcion: Mapped[str] = mapped_column(Text, nullable=False, default="",
        comment="Explicación del umbral para el usuario")

    def __repr__(self) -> str:
        return f"<KpiThreshold {self.kpi} {self.nivel}: {self.operador}{self.umbral}>"


# ── Coste Efectivo de Servicios (CESEL) ──────────────────────────────────────

class CeselKpi(Base):
    """
    KPIs de coste efectivo de servicios municipales calculados según la
    metodología CESEL del Ministerio de Hacienda.

    Cada fila representa un KPI (coste_total, coste_por_usuario, num_usuarios)
    para un servicio específico en un ejercicio. La fuente es el XLSX que los
    ayuntamientos remiten al Ministerio y que se publica en el portal de
    transparencia.

    El código CESEL identifica el servicio de forma normalizada a nivel nacional,
    lo que permite benchmarking entre municipios cuando los datos estén disponibles.
    """
    __tablename__ = "cesel_kpis"
    __table_args__ = (
        UniqueConstraint("nif_entidad", "ejercicio", "servicio", "kpi",
                         name="uq_cesel_entidad_ejercicio_servicio_kpi"),
        Index("ix_cesel_ejercicio", "ejercicio"),
        Index("ix_cesel_nif_ejercicio", "nif_entidad", "ejercicio"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nif_entidad: Mapped[str] = mapped_column(String(20), nullable=False)
    ejercicio: Mapped[int] = mapped_column(Integer, nullable=False)
    servicio: Mapped[str] = mapped_column(String(200), nullable=False,
        comment="Código o descripción normalizada del servicio CESEL")
    kpi: Mapped[str] = mapped_column(String(40), nullable=False,
        comment="'coste_total' | 'coste_por_usuario' | 'num_usuarios'")
    valor: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    fuente: Mapped[str] = mapped_column(String(60), nullable=False,
        comment="Fuente del dato, ej: 'transparencia_cesel_xlsx'")

    odmgr_dataset_id: Mapped[Optional[str]] = mapped_column(String(36))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<CeselKpi {self.nif_entidad} {self.ejercicio} {self.servicio} {self.kpi}={self.valor}>"


# ── Log de excepciones del ETL ────────────────────────────────────────────────

class EtlValidationException(Base):
    """
    Registra discrepancias detectadas al cruzar dos fuentes para el mismo KPI.

    Se genera automáticamente cuando validate_and_upsert_cgkpi() detecta que el
    valor entrante difiere del valor existente en más del umbral configurado, o
    cuando la fuente entrante tiene mayor prioridad y sobreescribe la existente.

    Estados de acción:
      kept_existing  — se mantuvo el valor existente (fuente entrante de menor prioridad)
      updated        — se actualizó al valor entrante (fuente entrante de mayor prioridad)
      pending        — ingestado pero pendiente de revisión manual
    """
    __tablename__ = "etl_validation_exceptions"
    __table_args__ = (
        Index("ix_etlexc_nif_ejercicio", "nif_entidad", "ejercicio"),
        Index("ix_etlexc_acknowledged", "acknowledged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nif_entidad: Mapped[str]          = mapped_column(String(20), nullable=False)
    ejercicio: Mapped[int]            = mapped_column(Integer, nullable=False)
    kpi: Mapped[str]                  = mapped_column(String(80), nullable=False)

    fuente_existente: Mapped[Optional[str]] = mapped_column(String(100))
    valor_existente:  Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    fuente_nueva: Mapped[Optional[str]] = mapped_column(String(100))
    valor_nuevo:  Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    diff_pct: Mapped[Optional[float]] = mapped_column(Float,
        comment="Diferencia relativa en %. Positivo = nuevo > existente.")
    diff_abs: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2),
        comment="Diferencia absoluta: valor_nuevo - valor_existente")

    accion: Mapped[str] = mapped_column(String(20), nullable=False, default="pending",
        comment="kept_existing | updated | pending")

    detected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ack_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EtlValidationException {self.nif_entidad} {self.ejercicio} "
            f"{self.kpi}: {self.fuente_existente}={self.valor_existente} "
            f"vs {self.fuente_nueva}={self.valor_nuevo} ({self.diff_pct:.1f}%)>"
        )

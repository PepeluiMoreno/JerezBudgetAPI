"""
Modelos ORM para datos socioeconómicos sincronizados desde OpenDataManager.

Solo se persisten localmente los datasets que JerezBudgetAPI necesita para JOINs SQL:
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
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
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
        UniqueConstraint("nif_entidad", "ejercicio", "kpi",
                         name="uq_cgkpi_entidad_ejercicio_kpi"),
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

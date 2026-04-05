"""
Schema de los ficheros CONPREL del Ministerio de Hacienda.

Los ficheros .mdb tienen una estructura que ha variado ligeramente
entre años. Este módulo centraliza todos los nombres de tabla y
columna conocidos para que el parser sea robusto ante esas variaciones.

Estructura típica del MDB (validada en ficheros 2010-2024):
  Tabla de gastos (capítulo): PRESUPUESTO_GASTOS_CAP o similar
  Tabla de ingresos (capítulo): PRESUPUESTO_INGRESOS_CAP o similar
  Tabla de programas (área funcional): PRESUPUESTO_GASTOS_FUNC

Columnas clave (con variantes por año):
  - Código entidad: CODENT, IDENT, COD_ENT
  - Código capítulo: CAPITULO, CAP, NCAP
  - Importe presupuesto: IMP_PRES, IMPORTE_PRES, PRESPUESTO
  - Importe liquidación gastos: OBLREC, OBL_RECONO, OBLIGACIONES
  - Importe liquidación ingresos: DERREC, DER_RECONO, DERECHOS
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DataType(StrEnum):
    BUDGET      = "budget"
    LIQUIDATION = "liquidation"


class Direction(StrEnum):
    EXPENSE = "expense"
    REVENUE = "revenue"


# ── Nombres de tabla por versión del MDB ─────────────────────────────────────
# Cada entrada es una lista de nombres alternativos (se prueba en orden).

TABLE_NAMES = {
    # Presupuesto de gastos por capítulo
    "budget_expense_chapter": [
        "PRESUPUESTO_GASTOS_CAP",
        "PPTO_GASTOS_CAP",
        "GASTOS_CAPITULO",
        "GASTOS_CAP",
        "T_GASTOS_CAP",
    ],
    # Liquidación de gastos por capítulo
    "liquidation_expense_chapter": [
        "LIQUIDACION_GASTOS_CAP",
        "LIQ_GASTOS_CAP",
        "GASTOS_LIQUIDACION_CAP",
        "EJEC_GASTOS_CAP",
    ],
    # Presupuesto de ingresos por capítulo
    "budget_revenue_chapter": [
        "PRESUPUESTO_INGRESOS_CAP",
        "PPTO_INGRESOS_CAP",
        "INGRESOS_CAPITULO",
        "INGRESOS_CAP",
        "T_INGRESOS_CAP",
    ],
    # Liquidación de ingresos por capítulo
    "liquidation_revenue_chapter": [
        "LIQUIDACION_INGRESOS_CAP",
        "LIQ_INGRESOS_CAP",
        "INGRESOS_LIQUIDACION_CAP",
        "EJEC_INGRESOS_CAP",
    ],
    # Clasificación funcional (área de gasto)
    "budget_program": [
        "PRESUPUESTO_GASTOS_FUNC",
        "PPTO_GASTOS_FUNC",
        "GASTOS_FUNCIONAL",
        "GASTOS_FUNC",
    ],
    "liquidation_program": [
        "LIQUIDACION_GASTOS_FUNC",
        "LIQ_GASTOS_FUNC",
        "EJEC_GASTOS_FUNC",
    ],
}

# ── Nombres de columna por significado ───────────────────────────────────────
# Lista en orden de preferencia (más moderno primero).

COLUMN_ALIASES = {
    # Código de la entidad local (código INE 5 dígitos o similar)
    "entity_code": [
        "CODENT", "COD_ENT", "IDENT", "CODMUN",
        "COD_MUNICIPIO", "MUNICIPIO", "ENTIDAD",
    ],
    # Nombre de la entidad
    "entity_name": [
        "NOMENT", "NOM_ENT", "NOMBRE", "DENOMINACION",
        "NOM_MUNICIPIO",
    ],
    # Capítulo económico (1 dígito)
    "chapter": [
        "CAPITULO", "CAP", "NCAP", "NUM_CAP",
        "CLASIF_CAPITULO", "CAPITULO_ECONOMICO",
    ],
    # Área funcional (1 dígito)
    "area": [
        "AREA", "NAREA", "AREA_FUNCIONAL", "CLASIF_AREA",
        "POLITICA",
    ],
    # ── Columnas de importe ───────────────────────────────────────────────
    # Créditos iniciales / Previsiones iniciales
    "initial_amount": [
        "IMP_PRES", "IMPORTE_PRES", "PRESUPUESTO", "PRESPUESTO",
        "CRED_INICIALES", "PREV_INICIALES", "INICIAL",
        "IMP_INICIAL", "CREDITO_INICIAL",
    ],
    # Créditos definitivos / Previsiones definitivas
    "final_amount": [
        "CRED_DEF", "CREDITO_DEFINITIVO", "IMP_DEF",
        "PREV_DEF", "PREV_DEFINITIVAS", "DEFINITIVO",
        "IMP_DEFINITIVO",
    ],
    # Obligaciones reconocidas netas (gastos ejecutados)
    "executed_expense": [
        "OBLREC", "OBL_RECONO", "OBLIGACIONES", "OBL_RECONOCIDAS",
        "OBLIG_NETAS", "EJEC_GASTOS", "IMP_OBLREC",
        "OBLIGACIONES_RECONOCIDAS",
    ],
    # Derechos reconocidos netos (ingresos ejecutados)
    "executed_revenue": [
        "DERREC", "DER_RECONO", "DERECHOS", "DER_RECONOCIDOS",
        "DER_NETOS", "EJEC_INGRESOS", "IMP_DERREC",
        "DERECHOS_RECONOCIDOS",
    ],
}


@dataclass
class ConprelRecord:
    """Una línea de datos extraída del MDB CONPREL."""
    entity_code: str            # Código entidad (será normalizado a INE 5 dígitos)
    entity_name: str
    chapter: str                # Capítulo 1 dígito ('1'-'9') o área funcional
    direction: Direction
    data_type: DataType
    initial_amount: float | None = None
    final_amount: float | None = None
    executed_amount: float | None = None
    # Metadatos de parseo
    table_name: str = ""
    fiscal_year: int = 0


# ── Nombres de áreas funcionales ICAL ────────────────────────────────────────
AREA_NAMES = {
    "1": "Servicios públicos básicos",
    "2": "Actuaciones de protección y promoción social",
    "3": "Producción de bienes públicos de carácter preferente",
    "4": "Actuaciones de carácter económico",
    "9": "Actuaciones de carácter general",
}

# ── Nombres de capítulos económicos ICAL ─────────────────────────────────────
CHAPTER_NAMES_EXPENSE = {
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
CHAPTER_NAMES_REVENUE = {
    "1": "Impuestos directos",
    "2": "Impuestos indirectos",
    "3": "Tasas y otros ingresos",
    "4": "Transferencias corrientes",
    "5": "Ingresos patrimoniales",
    "6": "Enajenación de inversiones reales",
    "7": "Transferencias de capital",
    "8": "Activos financieros",
    "9": "Pasivos financieros",
}

# ── URLs CONPREL por año ──────────────────────────────────────────────────────
# El Ministerio publica el fichero MDB anualmente.
# URL base: https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL/
# Las rutas exactas varían — se construyen dinámicamente en el downloader.
CONPREL_BASE_URL = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"

# Años disponibles en CONPREL
CONPREL_AVAILABLE_YEARS = list(range(2010, 2025))  # 2010-2024 (liquidación)

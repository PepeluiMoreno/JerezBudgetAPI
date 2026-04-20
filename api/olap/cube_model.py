"""
Modelos de cubo OLAP compatibles con la especificación babbage / OpenSpending.

Un modelo describe las dimensiones y medidas de un dataset.
Los frontends de babbage (babbage.ui, OS Viewer) consumen este
modelo para saber cómo construir queries de agregación.

Cuatro cubos expuestos:
  municipal-spain       → todos municipios, capítulo económico, 2010-2024
  municipal-spain-func  → todos municipios, área funcional, 2010-2024
  jerez-detail          → solo Jerez, económico mensual, 2020-2026
  jerez-rigor           → métricas IPP/ITP/ITR de Jerez, anual
"""
from __future__ import annotations

from typing import Any

# ── Tipos de cubo ────────────────────────────────────────────────────────────

CubeModel = dict[str, Any]   # alias para claridad


def _dim(label: str, key: str, **attrs) -> dict:
    """Construye una definición de dimensión babbage."""
    return {
        "label": label,
        "key_attribute": key,
        "label_attribute": attrs.pop("label_attr", key),
        "attributes": {
            key: {"column": attrs.pop("key_col", key), "label": label},
            **{k: {"column": v} for k, v in attrs.items()},
        },
    }


def _measure(label: str, column: str, type_: str = "monetary") -> dict:
    """Construye una definición de medida babbage."""
    return {"label": label, "column": column, "type": type_}


# ═══════════════════════════════════════════════════════════════════════════════
# CUBO 1 — municipal-spain
# Todos los municipios × capítulo económico × año (2010-2024)
# Fuente: CONPREL — Ministerio de Hacienda
# ═══════════════════════════════════════════════════════════════════════════════

MUNICIPAL_SPAIN_FACT_TABLE = """
    municipal_budget_chapters mbc
    JOIN municipal_budgets mb ON mbc.municipal_budget_id = mb.id
    JOIN municipalities m ON mb.municipality_id = m.id
    LEFT JOIN municipal_population mp
        ON mp.municipality_id = m.id AND mp.year = mb.fiscal_year
"""

MUNICIPAL_SPAIN_MODEL: CubeModel = {
    "fact_table": MUNICIPAL_SPAIN_FACT_TABLE,
    "dimensions": {
        "municipality": {
            "label": "Municipio",
            "key_attribute": "ine_code",
            "label_attribute": "name",
            "attributes": {
                "ine_code":      {"column": "m.ine_code",       "label": "Código INE"},
                "name":          {"column": "m.name",           "label": "Nombre"},
                "province_code": {"column": "m.province_code",  "label": "Código Provincia"},
                "province":      {"column": "m.province_name",  "label": "Provincia"},
                "ccaa_code":     {"column": "m.ccaa_code",      "label": "Código CCAA"},
                "ccaa":          {"column": "m.ccaa_name",      "label": "Comunidad Autónoma"},
                "population":    {"column": "mp.population",    "label": "Población"},
            },
        },
        "year": {
            "label": "Ejercicio fiscal",
            "key_attribute": "fiscal_year",
            "label_attribute": "fiscal_year",
            "attributes": {
                "fiscal_year": {"column": "mb.fiscal_year", "label": "Año"},
            },
        },
        "chapter": {
            "label": "Capítulo económico",
            "key_attribute": "chapter",
            "label_attribute": "chapter",
            "attributes": {
                "chapter":   {"column": "mbc.chapter",   "label": "Capítulo"},
                "direction": {"column": "mbc.direction", "label": "Tipo (gasto/ingreso)"},
            },
        },
        "data_type": {
            "label": "Tipo de dato",
            "key_attribute": "data_type",
            "label_attribute": "data_type",
            "attributes": {
                "data_type": {"column": "mb.data_type", "label": "Presupuesto o Liquidación"},
            },
        },
    },
    "measures": {
        "initial_amount": {
            "label": "Créditos / Previsiones iniciales (€)",
            "column": "mbc.initial_amount",
            "aggregation": "sum",
            "type": "monetary",
        },
        "executed_amount": {
            "label": "Obligaciones / Derechos reconocidos (€)",
            "column": "mbc.executed_amount",
            "aggregation": "sum",
            "type": "monetary",
        },
        "initial_per_capita": {
            "label": "€/hab. iniciales",
            "column": "mbc.initial_per_capita",
            "aggregation": "avg",
            "type": "monetary",
        },
        "executed_per_capita": {
            "label": "€/hab. ejecutados",
            "column": "mbc.executed_per_capita",
            "aggregation": "avg",
            "type": "monetary",
        },
        "execution_rate": {
            "label": "Tasa de ejecución",
            "column": "mbc.execution_rate",
            "aggregation": "avg",
            "type": "ratio",
        },
        "modification_rate": {
            "label": "Tasa de modificación",
            "column": "mbc.modification_rate",
            "aggregation": "avg",
            "type": "ratio",
        },
    },
    "currency": "EUR",
    "date_attribute": "year.fiscal_year",
}


# ═══════════════════════════════════════════════════════════════════════════════
# CUBO 2 — municipal-spain-func
# Todos los municipios × área funcional × año (2010-2024)
# ═══════════════════════════════════════════════════════════════════════════════

MUNICIPAL_SPAIN_FUNC_MODEL: CubeModel = {
    "fact_table": """
        municipal_budget_programs mbp
        JOIN municipal_budgets mb ON mbp.municipal_budget_id = mb.id
        JOIN municipalities m ON mb.municipality_id = m.id
        LEFT JOIN municipal_population mp
            ON mp.municipality_id = m.id AND mp.year = mb.fiscal_year
    """,
    "dimensions": {
        "municipality": MUNICIPAL_SPAIN_MODEL["dimensions"]["municipality"],
        "year":         MUNICIPAL_SPAIN_MODEL["dimensions"]["year"],
        "data_type":    MUNICIPAL_SPAIN_MODEL["dimensions"]["data_type"],
        "area": {
            "label": "Área funcional",
            "key_attribute": "area_code",
            "label_attribute": "area_name",
            "attributes": {
                "area_code": {"column": "mbp.area_code", "label": "Código área"},
                "area_name": {"column": "mbp.area_name", "label": "Área de gasto"},
            },
        },
    },
    "measures": {
        "initial_amount": {
            "label": "Importe inicial (€)",
            "column": "mbp.initial_amount",
            "aggregation": "sum",
            "type": "monetary",
        },
        "executed_amount": {
            "label": "Importe ejecutado (€)",
            "column": "mbp.executed_amount",
            "aggregation": "sum",
            "type": "monetary",
        },
        "executed_per_capita": {
            "label": "€/hab. ejecutados",
            "column": "mbp.executed_per_capita",
            "aggregation": "avg",
            "type": "monetary",
        },
        "execution_rate": {
            "label": "Tasa de ejecución",
            "column": "mbp.execution_rate",
            "aggregation": "avg",
            "type": "ratio",
        },
    },
    "currency": "EUR",
    "date_attribute": "year.fiscal_year",
}


# ═══════════════════════════════════════════════════════════════════════════════
# CUBO 3 — jerez-detail
# Solo Jerez, capítulo económico, snapshots mensuales 2020-2026
# Fuente: CityDashboard (budget_lines de transparencia.jerez.es)
# ═══════════════════════════════════════════════════════════════════════════════

JEREZ_DETAIL_MODEL: CubeModel = {
    "fact_table": """
        budget_lines bl
        JOIN budget_snapshots bs ON bl.snapshot_id = bs.id
        JOIN fiscal_years fy ON bs.fiscal_year_id = fy.id
        JOIN economic_classifications ec ON bl.economic_id = ec.id
        LEFT JOIN functional_classifications fc ON bl.functional_id = fc.id
        LEFT JOIN organic_classifications oc ON bl.organic_id = oc.id
    """,
    "dimensions": {
        "year": {
            "label": "Ejercicio fiscal",
            "key_attribute": "fiscal_year",
            "label_attribute": "fiscal_year",
            "attributes": {
                "fiscal_year":  {"column": "fy.year",           "label": "Año"},
                "is_extension": {"column": "fy.is_extension",   "label": "Prórroga"},
                "status":       {"column": "fy.status",         "label": "Estado"},
            },
        },
        "snapshot": {
            "label": "Corte de ejecución",
            "key_attribute": "snapshot_date",
            "label_attribute": "snapshot_date",
            "attributes": {
                "snapshot_date": {"column": "bs.snapshot_date", "label": "Fecha corte"},
                "phase":         {"column": "bs.phase",         "label": "Fase"},
            },
        },
        "chapter": {
            "label": "Capítulo económico",
            "key_attribute": "chapter",
            "label_attribute": "chapter",
            "attributes": {
                "chapter":     {"column": "ec.chapter",     "label": "Capítulo"},
                "economic_code": {"column": "ec.code",      "label": "Código económico"},
                "description": {"column": "ec.description", "label": "Descripción"},
                "direction":   {"column": "ec.direction",   "label": "Tipo"},
            },
        },
        "program": {
            "label": "Programa funcional",
            "key_attribute": "functional_code",
            "label_attribute": "program_description",
            "attributes": {
                "functional_code":   {"column": "fc.code",        "label": "Código programa"},
                "program_description": {"column": "fc.description", "label": "Programa"},
                "area":              {"column": "fc.area",         "label": "Área"},
            },
        },
        "section": {
            "label": "Sección orgánica",
            "key_attribute": "organic_code",
            "label_attribute": "organic_code",
            "attributes": {
                "organic_code": {"column": "oc.code",    "label": "Código orgánico"},
                "section":      {"column": "oc.section", "label": "Sección"},
            },
        },
    },
    "measures": {
        "initial_credits": {
            "label": "Créditos iniciales (€)",
            "column": "bl.initial_credits",
            "aggregation": "sum",
            "type": "monetary",
        },
        "modifications": {
            "label": "Modificaciones (€)",
            "column": "bl.modifications",
            "aggregation": "sum",
            "type": "monetary",
        },
        "final_credits": {
            "label": "Créditos definitivos (€)",
            "column": "bl.final_credits",
            "aggregation": "sum",
            "type": "monetary",
        },
        "recognized_obligations": {
            "label": "Obligaciones reconocidas (€)",
            "column": "bl.recognized_obligations",
            "aggregation": "sum",
            "type": "monetary",
        },
        "payments_made": {
            "label": "Pagos realizados (€)",
            "column": "bl.payments_made",
            "aggregation": "sum",
            "type": "monetary",
        },
        "initial_forecast": {
            "label": "Previsiones iniciales (€)",
            "column": "bl.initial_forecast",
            "aggregation": "sum",
            "type": "monetary",
        },
        "recognized_rights": {
            "label": "Derechos reconocidos (€)",
            "column": "bl.recognized_rights",
            "aggregation": "sum",
            "type": "monetary",
        },
    },
    "currency": "EUR",
    "date_attribute": "year.fiscal_year",
}


# ═══════════════════════════════════════════════════════════════════════════════
# CUBO 4 — jerez-rigor
# Métricas IPP/ITP/ITR de Jerez, anual 2020-2026
# Fuente: RigorMetrics calculadas por RigorMetricsService
# ═══════════════════════════════════════════════════════════════════════════════

JEREZ_RIGOR_MODEL: CubeModel = {
    "fact_table": """
        rigor_metrics rm
        JOIN fiscal_years fy ON rm.fiscal_year_id = fy.id
    """,
    "dimensions": {
        "year": {
            "label": "Ejercicio fiscal",
            "key_attribute": "fiscal_year",
            "label_attribute": "fiscal_year",
            "attributes": {
                "fiscal_year":  {"column": "fy.year",           "label": "Año"},
                "is_extension": {"column": "fy.is_extension",   "label": "Es prórroga"},
                "status":       {"column": "fy.status",         "label": "Estado"},
                "approval_delay_days": {
                    "column": "fy.approval_delay_days",
                    "label": "Días retraso aprobación",
                },
            },
        },
    },
    "measures": {
        "global_rigor_score": {
            "label": "Score Global de Rigor (0-100)",
            "column": "rm.global_rigor_score",
            "aggregation": "avg",
            "type": "ratio",
        },
        "precision_index": {
            "label": "IPP — Índice de Precisión (0-100)",
            "column": "rm.precision_index",
            "aggregation": "avg",
            "type": "ratio",
        },
        "timeliness_index": {
            "label": "ITP — Índice de Puntualidad (0-100)",
            "column": "rm.timeliness_index",
            "aggregation": "avg",
            "type": "ratio",
        },
        "transparency_index": {
            "label": "ITR — Índice de Transparencia (0-100)",
            "column": "rm.transparency_index",
            "aggregation": "avg",
            "type": "ratio",
        },
        "expense_execution_rate": {
            "label": "Tasa de ejecución de gasto",
            "column": "rm.expense_execution_rate",
            "aggregation": "avg",
            "type": "ratio",
        },
        "revenue_execution_rate": {
            "label": "Tasa de ejecución de ingresos",
            "column": "rm.revenue_execution_rate",
            "aggregation": "avg",
            "type": "ratio",
        },
        "modification_rate": {
            "label": "Tasa de modificación presupuestaria",
            "column": "rm.modification_rate",
            "aggregation": "avg",
            "type": "ratio",
        },
        "num_modifications": {
            "label": "Nº expedientes de modificación",
            "column": "rm.num_modifications",
            "aggregation": "sum",
            "type": "count",
        },
    },
    "currency": "EUR",
    "date_attribute": "year.fiscal_year",
}


# ── Registro de cubos disponibles ────────────────────────────────────────────

CUBE_REGISTRY: dict[str, dict] = {
    "municipal-spain": {
        "model":       MUNICIPAL_SPAIN_MODEL,
        "label":       "Presupuestos municipales españoles — capítulo económico",
        "description": "Todos los municipios de España. Presupuesto inicial y liquidación "
                       "por capítulo económico. Fuente: CONPREL (Ministerio de Hacienda). "
                       "Período 2010-2024.",
        "currency":    "EUR",
        "period":      "2010-2024",
        "granularity": "annual",
    },
    "municipal-spain-func": {
        "model":       MUNICIPAL_SPAIN_FUNC_MODEL,
        "label":       "Presupuestos municipales españoles — área funcional",
        "description": "Todos los municipios de España clasificados por área funcional ICAL. "
                       "Fuente: CONPREL. Período 2010-2024.",
        "currency":    "EUR",
        "period":      "2010-2024",
        "granularity": "annual",
    },
    "jerez-detail": {
        "model":       JEREZ_DETAIL_MODEL,
        "label":       "Presupuesto Jerez de la Frontera — detalle mensual",
        "description": "Ejecución presupuestaria del Ayuntamiento de Jerez de la Frontera "
                       "con granularidad mensual por aplicación presupuestaria. "
                       "Fuente: transparencia.jerez.es. Período 2020-2026.",
        "currency":    "EUR",
        "period":      "2020-2026",
        "granularity": "monthly",
    },
    "jerez-rigor": {
        "model":       JEREZ_RIGOR_MODEL,
        "label":       "Métricas de rigor presupuestario — Jerez de la Frontera",
        "description": "Índices IPP (Precisión), ITP (Puntualidad), ITR (Transparencia) "
                       "y Score Global de Rigor calculados para Jerez. Período 2020-2026.",
        "currency":    "EUR",
        "period":      "2020-2026",
        "granularity": "annual",
    },
}

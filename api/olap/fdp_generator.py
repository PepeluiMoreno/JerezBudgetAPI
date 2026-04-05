"""
Generador de Fiscal Data Package (FDP).
Compatible con la especificación frictionlessdata / OpenSpending.

El FDP es un ZIP con:
  - datapackage.json   → descriptor con metadatos y schema
  - expenses.csv       → gastos por capítulo
  - revenues.csv       → ingresos por capítulo
  - programs.csv       → áreas funcionales (si disponible)
  - rigor_metrics.csv  → métricas de rigor (extensión propia)
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

logger = structlog.get_logger(__name__)

JEREZ_INE = "11021"


async def generate_fdp(
    db: AsyncSession,
    cube_name: str,
    cube_info: dict,
) -> io.BytesIO:
    """
    Genera el ZIP del Fiscal Data Package para un cubo dado.
    Retorna un BytesIO listo para streaming.
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if cube_name == "municipal-spain":
            await _add_national_fdp(db, zf, cube_info)
        elif cube_name == "municipal-spain-func":
            await _add_national_func_fdp(db, zf, cube_info)
        elif cube_name in ("jerez-detail", "jerez-rigor"):
            await _add_jerez_fdp(db, zf, cube_name, cube_info)
        else:
            await _add_generic_fdp(db, zf, cube_name, cube_info)

    buf.seek(0)
    return buf


# ── FDP Nacional (municipal-spain) ────────────────────────────────────────────

async def _add_national_fdp(db: AsyncSession, zf: zipfile.ZipFile, info: dict):
    """FDP con datos de Jerez comparado con su grupo de pares."""
    # Solo exportamos Jerez + pares para no generar CSVs de 100MB
    result = await db.execute(text("""
        SELECT
            m.ine_code, m.name AS municipality_name,
            m.province_name, m.ccaa_name,
            mb.fiscal_year, mb.data_type,
            mbc.chapter, mbc.direction,
            mbc.initial_amount, mbc.executed_amount,
            mbc.executed_per_capita, mbc.execution_rate
        FROM municipalities m
        JOIN municipal_budgets mb ON mb.municipality_id = m.id
        JOIN municipal_budget_chapters mbc ON mbc.municipal_budget_id = mb.id
        JOIN peer_group_members pgm ON pgm.municipality_id = m.id
        JOIN peer_groups pg ON pg.id = pgm.peer_group_id
        WHERE pg.slug = 'andalucia-100k-250k'
          AND mb.data_type = 'liquidation'
        ORDER BY mb.fiscal_year, m.ine_code, mbc.chapter, mbc.direction
    """))
    rows = result.mappings().all()

    expense_rows = [r for r in rows if r["direction"] == "expense"]
    revenue_rows = [r for r in rows if r["direction"] == "revenue"]

    descriptor = _build_descriptor(
        name="jerez-peer-comparison",
        title="Jerez de la Frontera — Comparativa con municipios similares (Andalucía 100k-250k hab.)",
        description=(
            "Liquidaciones presupuestarias por capítulo económico de Jerez de la Frontera "
            "y municipios andaluces de tamaño similar (100.000-250.000 habitantes). "
            "Fuente: CONPREL — Ministerio de Hacienda."
        ),
        resources=[
            _expense_resource("expenses", "expenses.csv"),
            _revenue_resource("revenues", "revenues.csv"),
        ],
    )

    zf.writestr("datapackage.json", json.dumps(descriptor, ensure_ascii=False, indent=2))
    zf.writestr("expenses.csv", _rows_to_csv(expense_rows, _EXPENSE_FIELDS))
    zf.writestr("revenues.csv", _rows_to_csv(revenue_rows, _REVENUE_FIELDS))


# ── FDP Funcional ─────────────────────────────────────────────────────────────

async def _add_national_func_fdp(db: AsyncSession, zf: zipfile.ZipFile, info: dict):
    result = await db.execute(text("""
        SELECT
            m.ine_code, m.name AS municipality_name,
            mb.fiscal_year, mb.data_type,
            mbp.area_code, mbp.area_name,
            mbp.initial_amount, mbp.executed_amount,
            mbp.executed_per_capita, mbp.execution_rate
        FROM municipalities m
        JOIN municipal_budgets mb ON mb.municipality_id = m.id
        JOIN municipal_budget_programs mbp ON mbp.municipal_budget_id = mb.id
        JOIN peer_group_members pgm ON pgm.municipality_id = m.id
        JOIN peer_groups pg ON pg.id = pgm.peer_group_id
        WHERE pg.slug = 'andalucia-100k-250k'
          AND mb.data_type = 'liquidation'
        ORDER BY mb.fiscal_year, m.ine_code, mbp.area_code
    """))
    rows = result.mappings().all()

    descriptor = _build_descriptor(
        name="jerez-peer-functional",
        title="Jerez — Comparativa áreas funcionales con municipios similares",
        resources=[_program_resource("programs", "programs.csv")],
    )
    zf.writestr("datapackage.json", json.dumps(descriptor, ensure_ascii=False, indent=2))
    zf.writestr("programs.csv", _rows_to_csv(rows, _PROGRAM_FIELDS))


# ── FDP Jerez (detail + rigor) ────────────────────────────────────────────────

async def _add_jerez_fdp(
    db: AsyncSession, zf: zipfile.ZipFile,
    cube_name: str, info: dict
):
    resources = []

    if cube_name == "jerez-detail":
        exp = await db.execute(text("""
            SELECT
                fy.year AS fiscal_year, bs.snapshot_date,
                ec.chapter, ec.code AS economic_code,
                ec.description, ec.direction,
                bl.initial_credits, bl.modifications,
                bl.final_credits, bl.recognized_obligations,
                bl.payments_made,
                bl.initial_forecast, bl.final_forecast,
                bl.recognized_rights, bl.net_collection
            FROM budget_lines bl
            JOIN budget_snapshots bs ON bl.snapshot_id = bs.id
            JOIN fiscal_years fy ON bs.fiscal_year_id = fy.id
            JOIN economic_classifications ec ON bl.economic_id = ec.id
            ORDER BY fy.year, bs.snapshot_date, ec.direction, ec.chapter
        """))
        rows = exp.mappings().all()
        zf.writestr("budget_lines.csv", _rows_to_csv(rows, _JEREZ_DETAIL_FIELDS))
        resources.append({
            "name": "budget_lines",
            "path": "budget_lines.csv",
            "description": "Líneas presupuestarias de Jerez por fecha de corte",
        })

    elif cube_name == "jerez-rigor":
        rig = await db.execute(text("""
            SELECT
                fy.year AS fiscal_year,
                fy.is_extension,
                rm.expense_execution_rate,
                rm.revenue_execution_rate,
                rm.modification_rate,
                rm.num_modifications,
                rm.approval_delay_days,
                rm.publication_delay_days,
                rm.precision_index,
                rm.timeliness_index,
                rm.transparency_index,
                rm.global_rigor_score
            FROM rigor_metrics rm
            JOIN fiscal_years fy ON rm.fiscal_year_id = fy.id
            ORDER BY fy.year, rm.computed_at DESC
        """))
        rows = rig.mappings().all()
        zf.writestr("rigor_metrics.csv", _rows_to_csv(rows, _RIGOR_FIELDS))
        resources.append({
            "name": "rigor_metrics",
            "path": "rigor_metrics.csv",
            "description": "Índices IPP, ITP, ITR y Score Global de Jerez",
        })

    descriptor = _build_descriptor(
        name=f"jerez-{cube_name}",
        title=info["label"],
        description=info["description"],
        resources=resources,
    )
    zf.writestr("datapackage.json", json.dumps(descriptor, ensure_ascii=False, indent=2))


async def _add_generic_fdp(
    db: AsyncSession, zf: zipfile.ZipFile, name: str, info: dict
):
    """FDP genérico para cubos no específicamente manejados."""
    descriptor = _build_descriptor(
        name=name, title=info["label"], description=info.get("description", ""),
        resources=[]
    )
    zf.writestr("datapackage.json", json.dumps(descriptor, ensure_ascii=False, indent=2))


# ── Helpers ───────────────────────────────────────────────────────────────────

_EXPENSE_FIELDS = [
    "ine_code", "municipality_name", "province_name", "ccaa_name",
    "fiscal_year", "data_type", "chapter",
    "initial_amount", "executed_amount",
    "executed_per_capita", "execution_rate",
]
_REVENUE_FIELDS = _EXPENSE_FIELDS.copy()
_PROGRAM_FIELDS = [
    "ine_code", "municipality_name",
    "fiscal_year", "data_type", "area_code", "area_name",
    "initial_amount", "executed_amount",
    "executed_per_capita", "execution_rate",
]
_JEREZ_DETAIL_FIELDS = [
    "fiscal_year", "snapshot_date", "chapter", "economic_code",
    "description", "direction",
    "initial_credits", "modifications", "final_credits",
    "recognized_obligations", "payments_made",
    "initial_forecast", "final_forecast",
    "recognized_rights", "net_collection",
]
_RIGOR_FIELDS = [
    "fiscal_year", "is_extension",
    "expense_execution_rate", "revenue_execution_rate",
    "modification_rate", "num_modifications",
    "approval_delay_days", "publication_delay_days",
    "precision_index", "timeliness_index",
    "transparency_index", "global_rigor_score",
]


def _rows_to_csv(rows, fields: list[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=fields,
        extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fields})
    return out.getvalue()


def _build_descriptor(
    name: str,
    title: str,
    description: str = "",
    resources: list = None,
) -> dict:
    return {
        "name": name,
        "title": title,
        "description": description,
        "version": "1.0.0",
        "profile": "fiscal-data-package",
        "currency": "EUR",
        "countryCode": "ES",
        "publisher": {
            "name": "JerezBudget API — civic tech",
            "web": "https://github.com/PepeluiMoreno/JerezBudgetAPI",
        },
        "license": {
            "type": "odc-pddl",
            "url": "https://opendatacommons.org/licenses/pddl/",
        },
        "sources": [
            {
                "name": "CONPREL — Ministerio de Hacienda",
                "web": "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL",
            },
            {
                "name": "Portal de Transparencia — Ayuntamiento de Jerez",
                "web": "https://transparencia.jerez.es",
            },
        ],
        "created": datetime.utcnow().isoformat() + "Z",
        "resources": resources or [],
    }


def _expense_resource(name: str, path: str) -> dict:
    return {
        "name": name, "path": path,
        "schema": {
            "fields": [
                {"name": "ine_code",            "type": "string",  "columnType": "administrative-classification:generic:level1:code"},
                {"name": "municipality_name",   "type": "string",  "columnType": "administrative-classification:generic:level1:label"},
                {"name": "province_name",       "type": "string",  "columnType": "administrative-classification:generic:level2:label"},
                {"name": "ccaa_name",           "type": "string",  "columnType": "administrative-classification:generic:level3:label"},
                {"name": "fiscal_year",         "type": "integer", "columnType": "date:fiscal-year"},
                {"name": "data_type",           "type": "string"},
                {"name": "chapter",             "type": "string",  "columnType": "economic-classification:generic:level1:code"},
                {"name": "initial_amount",      "type": "number",  "columnType": "value", "phase": "approved"},
                {"name": "executed_amount",     "type": "number",  "columnType": "value", "phase": "executed"},
                {"name": "executed_per_capita", "type": "number",  "columnType": "value:per-capita"},
                {"name": "execution_rate",      "type": "number"},
            ]
        }
    }


def _revenue_resource(name: str, path: str) -> dict:
    r = _expense_resource(name, path)
    r["name"] = name
    r["path"] = path
    return r


def _program_resource(name: str, path: str) -> dict:
    return {
        "name": name, "path": path,
        "schema": {
            "fields": [
                {"name": "ine_code",            "type": "string",  "columnType": "administrative-classification:generic:level1:code"},
                {"name": "municipality_name",   "type": "string"},
                {"name": "fiscal_year",         "type": "integer", "columnType": "date:fiscal-year"},
                {"name": "data_type",           "type": "string"},
                {"name": "area_code",           "type": "string",  "columnType": "functional-classification:generic:level1:code"},
                {"name": "area_name",           "type": "string",  "columnType": "functional-classification:generic:level1:label"},
                {"name": "initial_amount",      "type": "number",  "columnType": "value", "phase": "approved"},
                {"name": "executed_amount",     "type": "number",  "columnType": "value", "phase": "executed"},
                {"name": "executed_per_capita", "type": "number",  "columnType": "value:per-capita"},
                {"name": "execution_rate",      "type": "number"},
            ]
        }
    }

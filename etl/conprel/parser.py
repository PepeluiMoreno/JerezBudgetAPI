"""
Parser de ficheros CONPREL (.mdb) del Ministerio de Hacienda.

Usa mdbtools para leer las tablas Access sin ODBC/Wine.
El fichero MDB contiene la siguiente estructura (verificado 2010-2024):

  tb_inventario      — catálogo de entidades: id → codbdgel ("01001AA000")
  tb_economica_cons  — presupuesto consolidado: id, tipreig, cdcta, importes
  tb_funcional_cons  — clasificación funcional consolidada: id, cdfgr, importes

Campos clave:
  tipreig: "G" = gastos (expense), "I" = ingresos (revenue)
  cdcta:   código económico (capítulo=1 dígito, artículo=2, concepto=3...)
  cdfgr:   código funcional  (área=1 dígito, política=2, grupo=3...)
  importer: crédito/previsión inicial
  imported: crédito/previsión definitiva
  importel: obligaciones/derechos reconocidos (liquidación)

El INE code (5 dígitos) se extrae de los primeros 5 chars de codbdgel.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import structlog

from etl.conprel.schema import (
    AREA_NAMES,
    ConprelRecord,
    DataType,
    Direction,
)

logger = structlog.get_logger(__name__)

# ── Constantes de tabla ───────────────────────────────────────────────────────
# Nombres reales del MDB (verificados 2010-2024).
# _CONS = versión consolidada (ayuntamiento + organismos autónomos).
# Sin _CONS = datos individuales por sub-entidad.
_TABLE_ECO   = "tb_economica_cons"   # presupuesto por clasificación económica
_TABLE_FUNC  = "tb_funcional_cons"   # presupuesto por clasificación funcional
_TABLE_INV   = "tb_inventario"       # catálogo entidades (id → INE code)

# Fallbacks si las tablas _cons no existen (años antiguos)
_TABLE_ECO_ALT  = "tb_economica"
_TABLE_FUNC_ALT = "tb_funcional"


@dataclass
class ParseStats:
    fiscal_year: int
    tables_found: list[str]
    tables_missing: list[str]
    records_extracted: int
    records_skipped: int
    municipalities_found: set[str]
    warnings: list[str]

    def __post_init__(self):
        if not isinstance(self.municipalities_found, set):
            self.municipalities_found = set(self.municipalities_found)
        if not isinstance(self.warnings, list):
            self.warnings = list(self.warnings)


# ── Helpers de bajo nivel ─────────────────────────────────────────────────────

def _check_mdbtools() -> bool:
    return shutil.which("mdb-export") is not None


def _list_tables(mdb_path: Path) -> list[str]:
    try:
        r = subprocess.run(
            ["mdb-tables", "-1", str(mdb_path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return [t.strip() for t in r.stdout.splitlines() if t.strip()]
    except subprocess.CalledProcessError as e:
        logger.error("mdb_tables_error", path=str(mdb_path), error=e.stderr)
        return []


def _export_df(mdb_path: Path, table: str) -> pd.DataFrame | None:
    """Exporta una tabla MDB a DataFrame. Retorna None si hay error."""
    try:
        r = subprocess.run(
            ["mdb-export", str(mdb_path), table],
            capture_output=True, text=True, check=True, timeout=300,
        )
        if not r.stdout.strip():
            return None
        df = pd.read_csv(io.StringIO(r.stdout), dtype=str, low_memory=False)
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except subprocess.CalledProcessError:
        return None
    except Exception as e:
        logger.warning("mdb_export_error", table=table, error=str(e))
        return None


def _pick_table(available: list[str], primary: str, fallback: str) -> str | None:
    """Elige la tabla disponible entre primary y fallback."""
    avail_lower = {t.lower(): t for t in available}
    for name in (primary, fallback):
        if name.lower() in avail_lower:
            return avail_lower[name.lower()]
    return None


def _to_float(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(" ", "").replace("\xa0", "")
    if s in ("", "nan", "NULL", "None"):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ── Extracción de datos ───────────────────────────────────────────────────────

def _build_ine_map(inv_df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """
    Construye el mapa id → (ine_code, entity_name) desde tb_inventario.

    codbdgel = "01001AA000" → INE code = "01001" (primeros 5 dígitos)
    """
    result: dict[str, tuple[str, str]] = {}
    for _, row in inv_df.iterrows():
        id_val    = str(row.get("id", "")).strip()
        codbdgel  = str(row.get("codbdgel",  row.get("codente", ""))).strip()
        name      = str(row.get("nombreppal", row.get("nombreente", ""))).strip()
        if len(codbdgel) >= 5 and codbdgel[:5].isdigit():
            ine = codbdgel[:5]
            result[id_val] = (ine, name)
    return result


def _chapter_from_cdcta(cdcta: str) -> str | None:
    """Extrae el capítulo (1 dígito) de un código económico."""
    s = cdcta.strip()
    if s and s[0].isdigit():
        return s[0]
    return None


def _area_from_cdfgr(cdfgr: str) -> str | None:
    """Extrae el área funcional (1 dígito) de un código funcional."""
    s = cdfgr.strip()
    if s and s[0].isdigit():
        return s[0]
    return None


def _aggregate_to_chapter(
    eco_df: pd.DataFrame,
    ine_map: dict[str, tuple[str, str]],
    fiscal_year: int,
) -> list[ConprelRecord]:
    """
    Convierte tb_economica_cons a ConprelRecords consolidados por capítulo e INE code.

    Múltiples entidades pueden compartir el mismo INE code (ayuntamiento + pedanías
    + organismos autónomos). Todas se suman para obtener el presupuesto consolidado.

    Estrategia de nivel:
      - Si existen filas de capítulo (cdcta de 1 dígito) → usar sólo esas.
      - Si no → agregar desde artículos/conceptos.
    """
    records: list[ConprelRecord] = []

    COL_INIT  = "importer"   # crédito/previsión inicial
    COL_FINAL = "imported"   # crédito/previsión definitivo
    COL_EXEC  = "importel"   # liquidación

    required = {"id", "tipreig", "cdcta", COL_EXEC}
    if missing := required - set(eco_df.columns):
        logger.warning("eco_missing_columns", missing=list(missing))
        return records

    eco_df = eco_df.copy()

    # Mapear id → ine_code (consolidar sub-entidades bajo mismo INE)
    id_to_ine = {k: v[0] for k, v in ine_map.items()}
    eco_df["ine_code"] = eco_df["id"].apply(lambda x: id_to_ine.get(str(x).strip()))
    eco_df = eco_df[eco_df["ine_code"].notna()].copy()

    # Extraer capítulo
    eco_df["chapter"]   = eco_df["cdcta"].apply(_chapter_from_cdcta)
    eco_df["cdcta_len"] = eco_df["cdcta"].str.strip().str.len()
    eco_df = eco_df[eco_df["chapter"].notna()].copy()

    # Convertir importes
    for col in (COL_INIT, COL_FINAL, COL_EXEC):
        eco_df[col] = eco_df.get(col, pd.Series(dtype=float)).apply(_to_float) \
            if col in eco_df.columns else None

    # Elegir nivel de detalle (global): capítulo si existe, artículo si no
    has_any_chapter_row = (eco_df["cdcta_len"] == 1).any()
    if has_any_chapter_row:
        use_rows = eco_df[eco_df["cdcta_len"] == 1]
    else:
        use_rows = eco_df

    # Agregar por (ine_code, tipreig, chapter) — consolida todas las sub-entidades
    agg = (
        use_rows
        .groupby(["ine_code", "tipreig", "chapter"])[[COL_INIT, COL_FINAL, COL_EXEC]]
        .sum(min_count=1)
        .reset_index()
    )

    for _, row in agg.iterrows():
        ine_code = str(row["ine_code"]).strip()
        tipreig  = str(row["tipreig"]).strip().upper()
        chapter  = str(row["chapter"]).strip()
        direction = Direction.EXPENSE if tipreig == "G" else Direction.REVENUE

        records.append(ConprelRecord(
            entity_code=ine_code,
            entity_name="",   # el nombre del municipio viene de la BD
            chapter=chapter,
            direction=direction,
            data_type=DataType.LIQUIDATION,
            initial_amount=row[COL_INIT]  if pd.notna(row[COL_INIT])  else None,
            final_amount=row[COL_FINAL]   if pd.notna(row[COL_FINAL]) else None,
            executed_amount=row[COL_EXEC] if pd.notna(row[COL_EXEC])  else None,
            table_name=_TABLE_ECO,
            fiscal_year=fiscal_year,
        ))

    return records


def _aggregate_to_area(
    func_df: pd.DataFrame,
    ine_map: dict[str, tuple[str, str]],
    fiscal_year: int,
) -> list[ConprelRecord]:
    """
    Convierte tb_funcional_cons a ConprelRecords por área funcional.
    """
    records: list[ConprelRecord] = []

    required = {"id", "cdfgr", "importe"}
    missing  = required - set(func_df.columns)
    if missing:
        logger.warning("func_missing_columns", missing=list(missing))
        return records

    func_df = func_df.copy()

    # Mapear id → ine_code
    id_to_ine = {k: v[0] for k, v in ine_map.items()}
    func_df["ine_code"] = func_df["id"].apply(lambda x: id_to_ine.get(str(x).strip()))
    func_df = func_df[func_df["ine_code"].notna()].copy()

    func_df["area"]     = func_df["cdfgr"].apply(_area_from_cdfgr)
    func_df             = func_df[func_df["area"].notna()].copy()
    func_df["importe"]  = func_df["importe"].apply(_to_float)
    func_df["cdfgr_len"] = func_df["cdfgr"].str.strip().str.len()

    has_any_area_row = (func_df["cdfgr_len"] == 1).any()
    if has_any_area_row:
        use_rows = func_df[func_df["cdfgr_len"] == 1]
    else:
        use_rows = func_df

    # Consolidar todas las sub-entidades bajo el mismo INE code
    agg = (
        use_rows
        .groupby(["ine_code", "area"])["importe"]
        .sum(min_count=1)
        .reset_index()
    )

    for _, row in agg.iterrows():
        ine_code = str(row["ine_code"]).strip()
        area     = str(row["area"]).strip()

        records.append(ConprelRecord(
            entity_code=ine_code,
            entity_name="",
            chapter=area,
            direction=Direction.EXPENSE,
            data_type=DataType.LIQUIDATION,
            executed_amount=row["importe"] if pd.notna(row["importe"]) else None,
            table_name=f"{_TABLE_FUNC}_FUNC",   # "FUNC" en el nombre → loader lo trata como área
            fiscal_year=fiscal_year,
        ))

    return records


# ── Punto de entrada público ──────────────────────────────────────────────────

def parse_conprel_mdb(
    mdb_path: Path,
    fiscal_year: int,
) -> tuple[list[ConprelRecord], ParseStats]:
    """
    Parsea un fichero MDB CONPREL completo.

    Devuelve (lista de ConprelRecord, estadísticas de parseo).
    """
    if not _check_mdbtools():
        raise RuntimeError("mdbtools no instalado: apt-get install -y mdbtools")

    stats = ParseStats(
        fiscal_year=fiscal_year,
        tables_found=[],
        tables_missing=[],
        records_extracted=0,
        records_skipped=0,
        municipalities_found=set(),
        warnings=[],
    )

    available = _list_tables(mdb_path)
    logger.info("mdb_tables_available", year=fiscal_year, tables=available)

    # ── tb_inventario (obligatorio) ───────────────────────────────────────────
    inv_table = _pick_table(available, _TABLE_INV, _TABLE_INV)
    if not inv_table:
        stats.tables_missing.append(_TABLE_INV)
        logger.error("inventario_table_missing", year=fiscal_year)
        return [], stats

    inv_df = _export_df(mdb_path, inv_table)
    if inv_df is None or inv_df.empty:
        logger.error("inventario_empty", year=fiscal_year)
        return [], stats

    stats.tables_found.append(inv_table)
    ine_map = _build_ine_map(inv_df)
    logger.info("ine_map_built", year=fiscal_year, entities=len(ine_map))

    all_records: list[ConprelRecord] = []

    # ── tb_economica_cons (clasificación económica) ───────────────────────────
    eco_table = _pick_table(available, _TABLE_ECO, _TABLE_ECO_ALT)
    if eco_table:
        stats.tables_found.append(eco_table)
        eco_df = _export_df(mdb_path, eco_table)
        if eco_df is not None and not eco_df.empty:
            logger.info("parsing_economica", year=fiscal_year, rows=len(eco_df))
            eco_records = _aggregate_to_chapter(eco_df, ine_map, fiscal_year)
            all_records.extend(eco_records)
            logger.info("economica_parsed", year=fiscal_year, records=len(eco_records))
        else:
            stats.warnings.append(f"{eco_table} vacía")
    else:
        stats.tables_missing.append(_TABLE_ECO)
        logger.warning("economica_table_missing", year=fiscal_year)

    # ── tb_funcional_cons (clasificación funcional) ───────────────────────────
    func_table = _pick_table(available, _TABLE_FUNC, _TABLE_FUNC_ALT)
    if func_table:
        stats.tables_found.append(func_table)
        func_df = _export_df(mdb_path, func_table)
        if func_df is not None and not func_df.empty:
            logger.info("parsing_funcional", year=fiscal_year, rows=len(func_df))
            func_records = _aggregate_to_area(func_df, ine_map, fiscal_year)
            all_records.extend(func_records)
            logger.info("funcional_parsed", year=fiscal_year, records=len(func_records))
    else:
        stats.tables_missing.append(_TABLE_FUNC)

    # ── Estadísticas finales ──────────────────────────────────────────────────
    stats.records_extracted = len(all_records)
    stats.municipalities_found = {r.entity_code for r in all_records}

    logger.info(
        "conprel_parse_done",
        year=fiscal_year,
        records=stats.records_extracted,
        municipalities=len(stats.municipalities_found),
        tables_found=stats.tables_found,
        tables_missing=stats.tables_missing,
    )

    return all_records, stats

"""
Parser de ficheros CONPREL (.mdb) del Ministerio de Hacienda.

Usa mdbtools (binario Linux) para leer las tablas Access sin necesidad
de ODBC, Wine o Windows. El binario `mdb-export` convierte cualquier
tabla a CSV con una sola llamada de subprocess.

Instalación del sistema:
    apt-get install -y mdbtools

Flujo:
    1. mdb-tables  → lista de tablas disponibles en el MDB
    2. mdb-export  → exporta tabla → CSV → pandas DataFrame
    3. Detecta columnas por alias → normaliza a ConprelRecord
    4. Filtra solo ayuntamientos (código entidad 5 dígitos)
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pandas as pd
import structlog

from etl.conprel.schema import (
    AREA_NAMES,
    CHAPTER_NAMES_EXPENSE,
    CHAPTER_NAMES_REVENUE,
    COLUMN_ALIASES,
    TABLE_NAMES,
    ConprelRecord,
    DataType,
    Direction,
)

logger = structlog.get_logger(__name__)

# Regex para detectar códigos de entidad local tipo INE (5 dígitos numéricos)
_INE_5_PATTERN = re.compile(r"^\d{5}$")
# Algunos años usan código de 9 dígitos: CCAA(2) + PROV(2) + ENTIDAD(5)
_INE_9_PATTERN = re.compile(r"^\d{9}$")


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


def _check_mdbtools() -> bool:
    """Verifica que mdbtools está instalado en el sistema."""
    return shutil.which("mdb-export") is not None


def _list_tables(mdb_path: Path) -> list[str]:
    """Lista todas las tablas disponibles en el MDB."""
    try:
        result = subprocess.run(
            ["mdb-tables", "-1", str(mdb_path)],
            capture_output=True, text=True, check=True, timeout=30
        )
        return [t.strip() for t in result.stdout.splitlines() if t.strip()]
    except subprocess.CalledProcessError as e:
        logger.error("mdb_tables_error", path=str(mdb_path), error=e.stderr)
        return []


def _export_table(mdb_path: Path, table_name: str) -> Optional[pd.DataFrame]:
    """
    Exporta una tabla MDB a DataFrame via mdb-export.
    Retorna None si la tabla no existe o hay error.
    """
    try:
        result = subprocess.run(
            ["mdb-export", str(mdb_path), table_name],
            capture_output=True, text=True, check=True, timeout=120
        )
        if not result.stdout.strip():
            return None
        df = pd.read_csv(io.StringIO(result.stdout), dtype=str, low_memory=False)
        df.columns = [str(c).strip().upper() for c in df.columns]
        return df
    except subprocess.CalledProcessError:
        return None
    except Exception as e:
        logger.warning("mdb_export_error", table=table_name, error=str(e))
        return None


def _find_column(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    """Encuentra el nombre real de una columna dado una lista de aliases."""
    cols_upper = {c.upper(): c for c in df.columns}
    for alias in aliases:
        if alias.upper() in cols_upper:
            return cols_upper[alias.upper()]
    return None


def _to_decimal(val) -> Optional[Decimal]:
    """Convierte valor a Decimal, None si vacío o no numérico."""
    if val is None or str(val).strip() in ("", "nan", "NULL", "None"):
        return None
    s = str(val).strip().replace(" ", "").replace("\xa0", "")
    # Formato europeo: 1.234.567,89
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _normalize_entity_code(raw: str) -> Optional[str]:
    """
    Normaliza el código de entidad a formato INE de 5 dígitos.
    - Si ya tiene 5 dígitos → usar tal cual
    - Si tiene 9 dígitos (CCAA+PROV+MUN) → tomar los últimos 5
    - Si tiene < 5 → padding con ceros a la izquierda
    - Si no es numérico → descartar
    """
    if not raw:
        return None
    code = re.sub(r"\D", "", str(raw).strip())  # solo dígitos
    if not code:
        return None
    if len(code) == 5:
        return code
    if len(code) == 9:
        # Los últimos 5 son provincia(2) + municipio(3)
        return code[4:]
    if len(code) < 5:
        return code.zfill(5)
    if len(code) > 5:
        # Truncar por la derecha buscando el INE de 5
        return code[-5:]
    return None


def _is_subtotal_like(row_values) -> bool:
    """
    Detecta filas de totales/subtotales que no son municipios reales.
    Se usa para filtrar filas de cabecera repetidas o resúmenes intermedios.
    """
    keywords = ("total", "suma", "capítulo", "capitulo", "subtotal")
    for val in row_values:
        if val and any(kw in str(val).lower() for kw in keywords):
            return True
    return False


def _parse_table(
    df: pd.DataFrame,
    table_key: str,
    direction: Direction,
    data_type: DataType,
    fiscal_year: int,
    table_name: str,
) -> tuple[list[ConprelRecord], int]:
    """
    Parsea un DataFrame de una tabla CONPREL y extrae ConprelRecords.
    Retorna (registros_válidos, filas_descartadas).
    """
    records: list[ConprelRecord] = []
    skipped = 0

    # Detectar columnas
    col_entity  = _find_column(df, COLUMN_ALIASES["entity_code"])
    col_name    = _find_column(df, COLUMN_ALIASES["entity_name"])
    col_chapter = _find_column(df, COLUMN_ALIASES["chapter"] if "chapter" in table_key else COLUMN_ALIASES["area"])
    col_initial = _find_column(df, COLUMN_ALIASES["initial_amount"])
    col_final   = _find_column(df, COLUMN_ALIASES["final_amount"])
    col_exec    = _find_column(df,
        COLUMN_ALIASES["executed_expense"] if direction == Direction.EXPENSE
        else COLUMN_ALIASES["executed_revenue"]
    )

    if not col_entity:
        logger.warning("no_entity_column", table=table_name, columns=list(df.columns)[:10])
        return [], len(df)

    for _, row in df.iterrows():
        raw_code = str(row.get(col_entity, "")).strip()
        ine_code = _normalize_entity_code(raw_code)

        # Solo ayuntamientos con código válido
        if not ine_code or not _INE_5_PATTERN.match(ine_code):
            skipped += 1
            continue

        raw_chapter = str(row.get(col_chapter, "")).strip() if col_chapter else ""
        chapter = re.sub(r"\D", "", raw_chapter)[:1]  # solo primer dígito
        if not chapter:
            skipped += 1
            continue

        entity_name = str(row.get(col_name, "")).strip() if col_name else ""
        initial  = _to_decimal(row.get(col_initial))  if col_initial else None
        final    = _to_decimal(row.get(col_final))    if col_final   else None
        executed = _to_decimal(row.get(col_exec))     if col_exec    else None

        records.append(ConprelRecord(
            entity_code=ine_code,
            entity_name=entity_name,
            chapter=chapter,
            direction=direction,
            data_type=data_type,
            initial_amount=float(initial) if initial is not None else None,
            final_amount=float(final)   if final   is not None else None,
            executed_amount=float(executed) if executed is not None else None,
            table_name=table_name,
            fiscal_year=fiscal_year,
        ))

    return records, skipped


def parse_conprel_mdb(mdb_path: Path, fiscal_year: int) -> tuple[list[ConprelRecord], ParseStats]:
    """
    Parsea un fichero MDB CONPREL completo.

    Args:
        mdb_path: Ruta al fichero .mdb
        fiscal_year: Año fiscal de los datos

    Returns:
        (lista de ConprelRecord, estadísticas de parseo)
    """
    if not _check_mdbtools():
        raise RuntimeError(
            "mdbtools no instalado. Ejecutar: apt-get install -y mdbtools"
        )

    stats = ParseStats(
        fiscal_year=fiscal_year,
        tables_found=[],
        tables_missing=[],
        records_extracted=0,
        records_skipped=0,
        municipalities_found=set(),
        warnings=[],
    )

    available_tables = _list_tables(mdb_path)
    logger.info("mdb_tables_available", year=fiscal_year, count=len(available_tables))

    all_records: list[ConprelRecord] = []

    # Definición de qué tablas parsear y con qué parámetros
    parse_plan = [
        ("budget_expense_chapter",      Direction.EXPENSE, DataType.BUDGET),
        ("liquidation_expense_chapter", Direction.EXPENSE, DataType.LIQUIDATION),
        ("budget_revenue_chapter",      Direction.REVENUE, DataType.BUDGET),
        ("liquidation_revenue_chapter", Direction.REVENUE, DataType.LIQUIDATION),
        ("budget_program",              Direction.EXPENSE, DataType.BUDGET),
        ("liquidation_program",         Direction.EXPENSE, DataType.LIQUIDATION),
    ]

    for table_key, direction, data_type in parse_plan:
        # Buscar el nombre real de la tabla probando aliases
        found_table = None
        for candidate in TABLE_NAMES[table_key]:
            if candidate in available_tables:
                found_table = candidate
                break
            # Búsqueda insensible a mayúsculas
            for t in available_tables:
                if t.upper() == candidate.upper():
                    found_table = t
                    break
            if found_table:
                break

        if not found_table:
            stats.tables_missing.append(table_key)
            logger.debug("table_not_found", key=table_key, year=fiscal_year)
            continue

        stats.tables_found.append(found_table)

        df = _export_table(mdb_path, found_table)
        if df is None or df.empty:
            stats.warnings.append(f"Tabla {found_table} vacía o con error")
            continue

        logger.debug(
            "parsing_table",
            table=found_table, rows=len(df), year=fiscal_year,
            direction=direction, data_type=data_type
        )

        records, skipped = _parse_table(
            df, table_key, direction, data_type, fiscal_year, found_table
        )
        all_records.extend(records)
        stats.records_extracted += len(records)
        stats.records_skipped   += skipped
        stats.municipalities_found.update(r.entity_code for r in records)

    logger.info(
        "conprel_parse_done",
        year=fiscal_year,
        records=stats.records_extracted,
        skipped=stats.records_skipped,
        municipalities=len(stats.municipalities_found),
        tables_found=len(stats.tables_found),
        tables_missing=len(stats.tables_missing),
    )

    return all_records, stats

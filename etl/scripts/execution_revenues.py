"""
etl/scripts/execution_revenues.py

Script de extracción para PdfPageFetcher de opendatamanager.
Parsea los XLSX de ejecución de ingresos presupuestarios.

Interfaz estándar ScriptFetcher:
  run(params: dict) -> list[dict]

Params esperados:
  pdf_dir   (required) — directorio con los XLSX descargados
  ejercicio (optional) — año fiscal, se añade a cada registro
"""
from __future__ import annotations

from pathlib import Path

from etl.parsers.xlsx_execution import parse_execution_xlsx


def run(params: dict) -> list[dict]:
    pdf_dir = params.get("pdf_dir")
    if not pdf_dir:
        raise ValueError("execution_revenues.run: 'pdf_dir' es obligatorio.")

    ejercicio = params.get("ejercicio")
    directorio = Path(pdf_dir)

    xlsx_files = sorted(directorio.glob("*.xlsx"))
    if not xlsx_files:
        return []

    records = []
    for xlsx_path in xlsx_files:
        result = parse_execution_xlsx(xlsx_path, hint_direction="revenue")

        if result.direction != "revenue":
            continue

        for line in result.lines:
            records.append({
                "ejercicio":          int(ejercicio) if ejercicio else None,
                "fichero":            xlsx_path.name,
                "snapshot_date":      _snapshot_from_filename(xlsx_path.name),
                "economic_code":      line.economic_code,
                "description":        line.description or None,
                "initial_forecast":   _to_float(line.initial_forecast),
                "modifications":      _to_float(line.modifications),
                "final_forecast":     _to_float(line.final_forecast),
                "recognized_rights":  _to_float(line.recognized_rights),
                "net_collection":     _to_float(line.net_collection),
                "pending_collection": _to_float(line.pending_collection),
            })

    return records


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_from_filename(filename: str) -> str | None:
    import re
    m = re.search(r"(\d{1,2})[-_](\d{2})[-_](\d{4})", filename)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1).zfill(2)}"
    return None

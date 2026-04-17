"""
etl/scripts/execution_expenses.py

Script de extracción para PdfPageFetcher de opendatamanager.
Parsea los XLSX de ejecución de gastos presupuestarios descargados
por el fetcher en pdf_dir.

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
        raise ValueError("execution_expenses.run: 'pdf_dir' es obligatorio.")

    ejercicio = params.get("ejercicio")
    directorio = Path(pdf_dir)

    xlsx_files = sorted(directorio.glob("*.xlsx"))
    if not xlsx_files:
        return []

    records = []
    for xlsx_path in xlsx_files:
        result = parse_execution_xlsx(xlsx_path, hint_direction="expense")

        if result.direction != "expense":
            # Saltar XLSX de ingresos que pudieran estar en el mismo directorio
            continue

        for line in result.lines:
            records.append({
                "ejercicio":              int(ejercicio) if ejercicio else None,
                "fichero":                xlsx_path.name,
                "snapshot_date":          _snapshot_from_filename(xlsx_path.name),
                "organic_code":           line.organic_code or None,
                "functional_code":        line.functional_code or None,
                "economic_code":          line.economic_code,
                "description":            line.description or None,
                "initial_credits":        _to_float(line.initial_credits),
                "modifications":          _to_float(line.modifications),
                "final_credits":          _to_float(line.final_credits),
                "commitments":            _to_float(line.commitments),
                "recognized_obligations": _to_float(line.recognized_obligations),
                "payments_made":          _to_float(line.payments_made),
                "pending_payment":        _to_float(line.pending_payment),
            })

    return records


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_from_filename(filename: str) -> str | None:
    """Extrae la fecha del nombre del fichero si la tiene (dd-mm-yyyy)."""
    import re
    m = re.search(r"(\d{1,2})[-_](\d{2})[-_](\d{4})", filename)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1).zfill(2)}"
    return None

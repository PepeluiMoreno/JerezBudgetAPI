"""
etl/scripts/budget_modifications.py

Script de extracción para PdfPageFetcher de opendatamanager.
Extrae metadatos de los PDFs de modificaciones presupuestarias.

Interfaz estándar ScriptFetcher:
  run(params: dict) -> list[dict]

Params esperados:
  pdf_dir   (required) — directorio con los PDFs descargados
  ejercicio (optional) — año fiscal, se añade a cada registro
"""
from __future__ import annotations

from pathlib import Path

from etl.parsers.pdf_metadata import extract_pdf_metadata


def run(params: dict) -> list[dict]:
    pdf_dir = params.get("pdf_dir")
    if not pdf_dir:
        raise ValueError("budget_modifications.run: 'pdf_dir' es obligatorio.")

    ejercicio = params.get("ejercicio")
    directorio = Path(pdf_dir)

    pdf_files = sorted(directorio.glob("*.pdf"))
    if not pdf_files:
        return []

    records = []
    for pdf_path in pdf_files:
        meta = extract_pdf_metadata(pdf_path)
        records.append({
            "ejercicio":        int(ejercicio) if ejercicio else None,
            "fichero":          pdf_path.name,
            "ref":              meta.ref,
            "mod_type":         meta.mod_type,
            "resolution_date":  str(meta.resolution_date) if meta.resolution_date else None,
            "publication_date": str(meta.publication_date) if meta.publication_date else None,
            "warnings":         "; ".join(meta.warnings) if meta.warnings else None,
        })

    return records

"""
Extractor de metadatos de PDFs presupuestarios.

No intenta parsear el contenido completo del PDF — solo extrae:
  - Fecha de firma / resolución (de la primera o última página)
  - Referencia del expediente (T003/2026)
  - Tipo inferido de modificación

Usa pdfplumber para acceso al texto. Robusto ante PDFs escaneados
(en ese caso devuelve None en los campos no extraídos).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# ── Patrones de extracción ───────────────────────────────────────────────────

# Fechas en formato español: "23 de marzo de 2026", "23/03/2026", "23-03-2026"
_DATE_PATTERNS = [
    re.compile(
        r"(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+(\d{4})",
        re.IGNORECASE,
    ),
    re.compile(r"(\d{1,2})[/-](\d{2})[/-](\d{4})"),
]

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Referencia de expediente
_MOD_REF = re.compile(r"T[-\s]?(\d{3})[/\-](\d{4})", re.IGNORECASE)

# Tipo de modificación por palabras clave en el texto
_MOD_TYPE_PATTERNS = [
    ("carry_forward",     re.compile(r"incorporaci[oó]n\s+de\s+remanentes", re.I)),
    ("generate",          re.compile(r"generaci[oó]n\s+de\s+cr[eé]dito", re.I)),
    ("transfer",          re.compile(r"transferencia\s+de\s+cr[eé]dito", re.I)),
    ("supplementary",     re.compile(r"suplemento\s+de\s+cr[eé]dito", re.I)),
    ("credit_reduction",  re.compile(r"minoraci[oó]n\s+de\s+cr[eé]dito", re.I)),
]


@dataclass
class PdfMetadata:
    ref: Optional[str] = None              # "T003/2026"
    mod_type: Optional[str] = None         # "transfer" | "generate" | ...
    resolution_date: Optional[date] = None
    publication_date: Optional[date] = None
    extracted_text_sample: str = ""        # primeros 500 chars para debug
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def _parse_spanish_date(text: str) -> Optional[date]:
    """Extrae la primera fecha válida del texto."""
    # Formato largo: "23 de marzo de 2026"
    for m in _DATE_PATTERNS[0].finditer(text):
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = _MONTHS.get(month_name)
        if month and 2015 <= year <= 2030:
            try:
                return date(year, month, day)
            except ValueError:
                continue

    # Formato corto: "23/03/2026"
    for m in _DATE_PATTERNS[1].finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2015 <= year <= 2030:
            try:
                return date(year, month, day)
            except ValueError:
                continue

    return None


def extract_pdf_metadata(path: Path) -> PdfMetadata:
    """
    Extrae metadatos de un PDF presupuestario.
    Analiza la primera página y la última buscando fechas de firma.
    """
    meta = PdfMetadata()

    try:
        import pdfplumber
    except ImportError:
        meta.warnings.append("pdfplumber no disponible — instalar con: pip install pdfplumber")
        return meta

    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                meta.warnings.append("PDF sin páginas")
                return meta

            # Extraer texto de primera y última página (firma suele estar al final)
            pages_to_check = [pdf.pages[0]]
            if len(pdf.pages) > 1:
                pages_to_check.append(pdf.pages[-1])

            full_text = ""
            for page in pages_to_check:
                text = page.extract_text() or ""
                full_text += text + "\n"

            if not full_text.strip():
                meta.warnings.append("No se pudo extraer texto (posible PDF escaneado)")
                return meta

            meta.extracted_text_sample = full_text[:500]

            # Referencia del expediente
            ref_match = _MOD_REF.search(full_text)
            if ref_match:
                meta.ref = f"T{ref_match.group(1)}/{ref_match.group(2)}"

            # Tipo de modificación
            for mod_type, pattern in _MOD_TYPE_PATTERNS:
                if pattern.search(full_text):
                    meta.mod_type = mod_type
                    break

            # Fecha de resolución (primera fecha significativa que aparezca)
            meta.resolution_date = _parse_spanish_date(full_text)

            logger.info(
                "pdf_metadata_extracted",
                file=path.name,
                ref=meta.ref,
                mod_type=meta.mod_type,
                resolution_date=meta.resolution_date,
            )

    except Exception as e:
        logger.warning("pdf_extract_error", path=str(path), error=str(e))
        meta.warnings.append(f"Error al procesar PDF: {e}")

    return meta

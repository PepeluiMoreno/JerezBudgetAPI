"""
Scraper del portal de transparencia del Ayuntamiento de Jerez.
Descubre ficheros XLSX (ejecución) y PDFs (modificaciones, documentos
presupuestarios) publicados en transparencia.jerez.es.

Estrategia:
  - Parsea la página HTML de cada año fiscal
  - Extrae enlaces a XLSX y PDF con sus metadatos
  - Compara contra los ya ingestados (por URL + hash) para evitar re-descargas
  - Es respetuoso con el servidor: delay entre requests, User-Agent informativo
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class FileType(StrEnum):
    EXECUTION_EXPENSES = "execution_expenses"
    EXECUTION_REVENUES = "execution_revenues"
    MODIFICATION = "modification"
    STABILITY_REPORT = "stability_report"
    EXTENSION_RESOLUTION = "extension_resolution"
    MEMORY = "memory"
    OTHER_PDF = "other_pdf"


@dataclass
class DiscoveredFile:
    url: str
    filename: str
    file_type: FileType
    fiscal_year: int
    snapshot_date: Optional[date] = None   # para XLSX de ejecución
    mod_ref: Optional[str] = None          # para modificaciones: "T003/2026"
    raw_label: str = ""


# ── URLs de cada año fiscal ──────────────────────────────────────────────────
YEAR_URLS: dict[int, str] = {
    2020: "/infopublica/economica/presupuesto/2020",
    2021: "/infopublica/economica/presupuesto/2021",
    2022: "/infopublica/economica/presupuesto/2022",
    2023: "/infopublica/economica/presupuesto/2023",
    2024: "/infopublica/economica/presupuesto/2024",
    2025: "/infopublica/economica/presupuesto/2025",
    2026: "/infopublica/economica/presupuesto/2026/prorroga-2025",
}

# Patrones para detectar tipo de fichero por nombre/etiqueta
_PATTERNS = [
    (FileType.EXECUTION_EXPENSES,  re.compile(r"[Gg]astos.*por.*aplicaciones|[Ee]jecuci[oó]n.*[Gg]astos", re.I)),
    (FileType.EXECUTION_REVENUES,  re.compile(r"[Ii]ngresos.*por.*aplicaciones|[Ee]jecuci[oó]n.*[Ii]ngresos", re.I)),
    (FileType.MODIFICATION,        re.compile(r"T\d{3}/\d{4}|[Mm]odificaci[oó]n|[Tt]ransferencia|[Rr]emanente|[Gg]eneraci[oó]n.*[Cc]r[eé]dito", re.I)),
    (FileType.STABILITY_REPORT,    re.compile(r"[Ee]stabilidad|AIREF|[Gg]astos.*regla", re.I)),
    (FileType.EXTENSION_RESOLUTION,re.compile(r"[Pp]r[oó]rroga|[Ee]xtensi[oó]n", re.I)),
    (FileType.MEMORY,              re.compile(r"[Mm]emoria.*econ[oó]mica|[Mm]emoria.*presupuest", re.I)),
]

# Extrae fecha del nombre de fichero:  _a_23-03-2026  o  _23-03-2026_
_DATE_IN_FILENAME = re.compile(r"(\d{1,2})[-_](\d{2})[-_](\d{4})")
# Referencia de modificación: T003/2026 o T003-2026
_MOD_REF = re.compile(r"T(\d{3})[-/](\d{4})", re.I)


def _detect_file_type(label: str, filename: str, ext: str) -> FileType:
    text = f"{label} {filename}"
    if ext in (".xlsx", ".xls"):
        for ftype, pat in _PATTERNS[:2]:
            if pat.search(text):
                return ftype
        return FileType.EXECUTION_EXPENSES  # hoja de cálculo por defecto
    for ftype, pat in _PATTERNS:
        if pat.search(text):
            return ftype
    return FileType.OTHER_PDF


def _extract_snapshot_date(filename: str, fiscal_year: int) -> Optional[date]:
    m = _DATE_IN_FILENAME.search(filename)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _extract_mod_ref(label: str, filename: str) -> Optional[str]:
    m = _MOD_REF.search(f"{label} {filename}")
    if m:
        return f"T{m.group(1)}/{m.group(2)}"
    return None


class TransparenciaScraper:
    """
    Descubre ficheros publicados en el portal de transparencia de Jerez.
    Thread-safe para uso desde Celery workers.
    """

    def __init__(self, base_url: str = settings.transparencia_base_url):
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "TransparenciaScraper":
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.http_user_agent},
            timeout=settings.http_timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_):
        if self._client:
            await self._client.aclose()

    async def _get(self, url: str) -> str:
        """GET con retry exponencial (3 intentos)."""
        assert self._client, "Usar como context manager"
        for attempt in range(3):
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise
                wait = 2 ** attempt
                logger.warning("scraper_retry", url=url, attempt=attempt + 1, wait=wait, error=str(e))
                await asyncio.sleep(wait)
        return ""  # unreachable

    def _parse_page(self, html: str, fiscal_year: int) -> list[DiscoveredFile]:
        """Extrae todos los enlaces a XLSX y PDF de la página de un año fiscal."""
        soup = BeautifulSoup(html, "lxml")
        discovered: list[DiscoveredFile] = []

        for a_tag in soup.find_all("a", href=True):
            href: str = a_tag["href"]
            ext = Path(href).suffix.lower()
            if ext not in (".xlsx", ".xls", ".pdf"):
                continue

            full_url = urljoin(self.base_url, href)
            filename = Path(urlparse(href).path).name
            label = a_tag.get_text(strip=True)
            # Incluir texto del párrafo padre para contexto
            parent_text = ""
            if a_tag.parent:
                parent_text = a_tag.parent.get_text(" ", strip=True)[:200]
            combined_label = f"{label} {parent_text}"

            ftype = _detect_file_type(combined_label, filename, ext)
            snap_date = _extract_snapshot_date(filename, fiscal_year) if ext in (".xlsx", ".xls") else None
            mod_ref = _extract_mod_ref(combined_label, filename) if ftype == FileType.MODIFICATION else None

            discovered.append(DiscoveredFile(
                url=full_url,
                filename=filename,
                file_type=ftype,
                fiscal_year=fiscal_year,
                snapshot_date=snap_date,
                mod_ref=mod_ref,
                raw_label=label[:200],
            ))
            logger.debug("discovered_file", year=fiscal_year, type=ftype, filename=filename)

        return discovered

    async def discover_year(self, fiscal_year: int) -> list[DiscoveredFile]:
        """Descubre todos los ficheros publicados para un año fiscal concreto."""
        path = YEAR_URLS.get(fiscal_year)
        if not path:
            logger.warning("unknown_year", year=fiscal_year)
            return []

        url = self.base_url + path
        logger.info("scraping_year", year=fiscal_year, url=url)
        html = await self._get(url)

        files = self._parse_page(html, fiscal_year)
        logger.info("year_discovery_done", year=fiscal_year, count=len(files))
        return files

    async def discover_all(
        self,
        years: Optional[list[int]] = None,
        delay_seconds: float = 1.5,
    ) -> list[DiscoveredFile]:
        """
        Descubre ficheros de todos los años (o los indicados).
        Respeta un delay entre requests para no saturar el servidor.
        """
        target_years = years or list(YEAR_URLS.keys())
        all_files: list[DiscoveredFile] = []

        for i, year in enumerate(target_years):
            files = await self.discover_year(year)
            all_files.extend(files)
            if i < len(target_years) - 1:
                await asyncio.sleep(delay_seconds)

        logger.info("discovery_complete", total_files=len(all_files))
        return all_files

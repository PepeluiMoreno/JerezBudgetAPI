"""
Descargador de población municipal del INE.

Fuente: INE Padrón Municipal de Habitantes
Tabla: 29005 (Cifras oficiales del padrón por municipio)

Estrategia eficiente (bulk):
  - Descarga la tabla completa UNA SOLA VEZ → 1 llamada HTTP en lugar de 8132
  - Parsea todos los municipios en una pasada usando MetaData
  - Tiempo: ~30-60 segundos vs ~2 horas del enfoque anterior

Estructura de la respuesta INE:
  - 24414 series (8138 municipios × 3 sexos: Total, Hombres, Mujeres)
  - MetaData plano: [{"T3_Variable": "Municipios", "Codigo": "11020", ...}, ...]
  - Data: [{"Anyo": 2024, "Valor": 213688.0}, ...]
"""
from __future__ import annotations

from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

INE_API_BASE    = "https://servicios.ine.es/wstempus/js/ES"
PADRON_TABLE_ID = "29005"           # Cifras oficiales del padrón por municipio
PADRON_YEARS    = list(range(2010, 2026))


# ── Helpers de parseo ─────────────────────────────────────────────────────────

def _extract_municipality_code(serie: dict) -> Optional[str]:
    """
    Extrae el código INE de 5 dígitos (PPMM) del municipio desde MetaData.

    MetaData del INE es una lista plana de dicts con campos:
      T3_Variable, Nombre, Codigo, Id
    """
    for m in serie.get("MetaData", []):
        if m.get("T3_Variable") == "Municipios":
            codigo = str(m.get("Codigo", "")).strip()
            if len(codigo) == 5 and codigo.isdigit():
                return codigo
    return None


def _is_total_sex(serie: dict) -> bool:
    """
    Devuelve True si la serie es del total (todos los sexos).
    Sexo.Codigo == "0" → Total; "1" → Hombres; "2" → Mujeres.
    """
    for m in serie.get("MetaData", []):
        if m.get("T3_Variable") == "Sexo":
            return m.get("Codigo") == "0"
    return True   # sin variable sexo → asumir total


# ── Descarga masiva (principal) ───────────────────────────────────────────────

async def fetch_all_population_bulk(
    years: Optional[list[int]] = None,
) -> dict[str, dict[int, int]]:
    """
    Descarga la tabla completa del padrón municipal del INE en una sola llamada.

    Una sola llamada HTTP cubre todos los ~8138 municipios, eliminando las
    8132 llamadas individuales que tardaban ~2 horas.

    Returns:
        Dict {ine_code_5_digitos: {año: población}}
    """
    target_years = set(years or PADRON_YEARS)

    url    = f"{INE_API_BASE}/DATOS_TABLA/{PADRON_TABLE_ID}"
    params = {
        "tip":  "AM",   # todos los periodos con metadatos completos
        "nult": "20",   # últimos 20 años (2005-2025)
    }

    logger.info("ine_bulk_download_start", table=PADRON_TABLE_ID)

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    logger.info("ine_bulk_downloaded", series_count=len(data))

    results: dict[str, dict[int, int]] = {}
    skipped_no_code   = 0
    skipped_not_total = 0

    for serie in data:
        ine_code = _extract_municipality_code(serie)
        if not ine_code:
            skipped_no_code += 1
            continue

        # Solo la serie "Total" (Sexo.Codigo == "0") para no duplicar
        if not _is_total_sex(serie):
            skipped_not_total += 1
            continue

        pop_by_year: dict[int, int] = {}
        for dato in serie.get("Data", []):
            anyo  = dato.get("Anyo")             # campo directo, sin parsear texto
            valor = dato.get("Valor")
            if anyo and valor is not None and int(anyo) in target_years:
                try:
                    pop_by_year[int(anyo)] = int(float(valor))
                except (ValueError, TypeError):
                    pass

        if pop_by_year:
            results[ine_code] = pop_by_year

    logger.info(
        "ine_bulk_parse_complete",
        municipalities_found=len(results),
        skipped_no_code=skipped_no_code,
        skipped_not_total=skipped_not_total,
    )
    return results


# ── Función de compatibilidad ─────────────────────────────────────────────────

async def fetch_population_batch(
    ine_codes: list[str],
    years: Optional[list[int]] = None,
    delay: float = 0.5,          # mantenido por compatibilidad, no se usa
) -> dict[str, dict[int, int]]:
    """
    Descarga la población para una lista de municipios.
    Usa fetch_all_population_bulk internamente (1 llamada HTTP total).
    """
    bulk = await fetch_all_population_bulk(years)
    return {code: bulk.get(code, {}) for code in ine_codes}


# ── Upsert ────────────────────────────────────────────────────────────────────

async def upsert_population(
    db,
    municipality_id: int,
    population_by_year: dict[int, int],
) -> int:
    """Inserta o actualiza la serie histórica de población en la BD."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from models.national import MunicipalPopulation

    if not population_by_year:
        return 0

    batch = [
        {
            "municipality_id": municipality_id,
            "year":            year,
            "population":      pop,
            "source":          "INE_PADRON",
        }
        for year, pop in population_by_year.items()
    ]

    stmt = pg_insert(MunicipalPopulation).values(batch).on_conflict_do_update(
        constraint="uq_mun_pop_year",
        set_={"population": pg_insert(MunicipalPopulation).excluded.population},
    )
    await db.execute(stmt)
    return len(batch)

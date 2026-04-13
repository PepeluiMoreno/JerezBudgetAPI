"""
Descargador de población municipal del INE.

Fuente: INE Padrón Municipal de Habitantes
API: https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/2852

El padrón municipal se publica anualmente (referencia 1 de enero).
Los datos de un año X se publican en el verano del año X+1.
Ejemplo: padrón 2024 publicado en 2025.

Estrategia:
  - Descarga la serie completa de la tabla 2852 (padrón por municipio y año)
  - Filtra por código INE del municipio
  - Inserta en municipal_population con upsert
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# URL base del API JSON del INE
INE_API_BASE = "https://servicios.ine.es/wstempus/js/ES"

# Tabla del padrón municipal (2852 = Cifras de Población por municipio)
PADRON_TABLE_ID = "2852"

# Años disponibles (el padrón se actualiza hasta ~año anterior)
PADRON_YEARS = list(range(2010, 2026))


async def fetch_population_ine_code(
    ine_code: str,
    years: Optional[list[int]] = None,
) -> dict[int, int]:
    """
    Obtiene la serie histórica de población para un municipio dado.

    Args:
        ine_code: Código INE de 5 dígitos ('11020' para Jerez)
        years: Lista de años a obtener (None = todos disponibles)

    Returns:
        Dict {año: población}
    """
    target_years = set(years or PADRON_YEARS)

    # El API del INE acepta el código municipio como parámetro
    # Endpoint: /DATOS_TABLA/{tabla}?tp=AM&nult={n_ultimos}
    # También: /DATOS_MUNICIPIO/{cod_municipio}
    url = f"{INE_API_BASE}/DATOS_TABLA/{PADRON_TABLE_ID}"
    params = {
        "tip": "AM",       # todos los periodos disponibles
        "nult": "20",      # últimos 20 periodos
    }

    result: dict[int, int] = {}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        # La respuesta es una lista de series temporales
        # Filtramos la que corresponde a nuestro municipio
        for serie in data:
            # El nombre de la serie contiene el municipio: "Jerez de la Frontera"
            # y el código: "11020"
            nombre = str(serie.get("Nombre", ""))
            if ine_code not in nombre and ine_code not in str(serie.get("COD", "")):
                continue

            for dato in serie.get("Data", []):
                anyo = _extract_year(dato.get("NombrePeriodo", ""))
                valor = dato.get("Valor")
                if anyo and valor and anyo in target_years:
                    result[anyo] = int(float(str(valor).replace(",", ".")))

    except Exception as e:
        logger.warning("ine_population_api_error", ine_code=ine_code, error=str(e))

    if not result:
        # Fallback: valores estimados desde datos del catálogo
        logger.warning("ine_population_no_data", ine_code=ine_code)

    logger.debug("population_fetched", ine_code=ine_code, years=sorted(result.keys()))
    return result


def _extract_year(periodo: str) -> Optional[int]:
    """Extrae el año de strings como '2023', '1 de enero de 2023'."""
    import re
    m = re.search(r"\b(20\d{2})\b", str(periodo))
    if m:
        return int(m.group(1))
    return None


async def fetch_population_batch(
    ine_codes: list[str],
    years: Optional[list[int]] = None,
    delay: float = 0.5,
) -> dict[str, dict[int, int]]:
    """
    Descarga la población para una lista de municipios.
    Respeta un delay entre requests para no saturar la API del INE.

    Returns:
        Dict {ine_code: {year: population}}
    """
    results: dict[str, dict[int, int]] = {}

    for i, code in enumerate(ine_codes):
        pop = await fetch_population_ine_code(code, years)
        results[code] = pop
        if i < len(ine_codes) - 1:
            await asyncio.sleep(delay)

    return results


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
        set_={"population": pg_insert(MunicipalPopulation).excluded.population}
    )
    await db.execute(stmt)
    return len(batch)

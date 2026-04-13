"""
Cargador del catálogo oficial de municipios del INE.

Fuente: INE — Relación de Municipios y sus Códigos por Provincias
URL CSV: https://www.ine.es/daco/daco42/codmun/codmun24.xlsx
  (actualizado anualmente; también disponible en TXT pipe-separated)

El catálogo tiene ~8.131 municipios con:
  - Código CPRO (provincia, 2 dígitos)
  - Código CMUN (municipio, 3 dígitos)
  - Código INE = CPRO + CMUN (5 dígitos)
  - Nombre del municipio
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import structlog
import pandas as pd

logger = structlog.get_logger(__name__)

# ── Datos estáticos de provincias y CCAA ────────────────────────────────────
# Mapa código provincia (2 dígitos) → (nombre provincia, código CCAA, nombre CCAA)
PROVINCE_MAP: dict[str, tuple[str, str, str]] = {
    "01": ("Álava",              "16", "País Vasco"),
    "02": ("Albacete",           "08", "Castilla-La Mancha"),
    "03": ("Alicante",           "10", "Comunitat Valenciana"),
    "04": ("Almería",            "01", "Andalucía"),
    "05": ("Ávila",              "07", "Castilla y León"),
    "06": ("Badajoz",            "11", "Extremadura"),
    "07": ("Balears (Illes)",    "04", "Illes Balears"),
    "08": ("Barcelona",          "09", "Catalunya"),
    "09": ("Burgos",             "07", "Castilla y León"),
    "10": ("Cáceres",            "11", "Extremadura"),
    "11": ("Cádiz",              "01", "Andalucía"),
    "12": ("Castellón",          "10", "Comunitat Valenciana"),
    "13": ("Ciudad Real",        "08", "Castilla-La Mancha"),
    "14": ("Córdoba",            "01", "Andalucía"),
    "15": ("Coruña (A)",         "12", "Galicia"),
    "16": ("Cuenca",             "08", "Castilla-La Mancha"),
    "17": ("Girona",             "09", "Catalunya"),
    "18": ("Granada",            "01", "Andalucía"),
    "19": ("Guadalajara",        "08", "Castilla-La Mancha"),
    "20": ("Gipuzkoa",           "16", "País Vasco"),
    "21": ("Huelva",             "01", "Andalucía"),
    "22": ("Huesca",             "02", "Aragón"),
    "23": ("Jaén",               "01", "Andalucía"),
    "24": ("León",               "07", "Castilla y León"),
    "25": ("Lleida",             "09", "Catalunya"),
    "26": ("Rioja (La)",         "17", "La Rioja"),
    "27": ("Lugo",               "12", "Galicia"),
    "28": ("Madrid",             "13", "Comunidad de Madrid"),
    "29": ("Málaga",             "01", "Andalucía"),
    "30": ("Murcia",             "14", "Región de Murcia"),
    "31": ("Navarra",            "15", "Comunidad Foral de Navarra"),
    "32": ("Ourense",            "12", "Galicia"),
    "33": ("Asturias",           "03", "Principado de Asturias"),
    "34": ("Palencia",           "07", "Castilla y León"),
    "35": ("Palmas (Las)",       "05", "Canarias"),
    "36": ("Pontevedra",         "12", "Galicia"),
    "37": ("Salamanca",          "07", "Castilla y León"),
    "38": ("Santa Cruz Tenerife","05", "Canarias"),
    "39": ("Cantabria",          "06", "Cantabria"),
    "40": ("Segovia",            "07", "Castilla y León"),
    "41": ("Sevilla",            "01", "Andalucía"),
    "42": ("Soria",              "07", "Castilla y León"),
    "43": ("Tarragona",          "09", "Catalunya"),
    "44": ("Teruel",             "02", "Aragón"),
    "45": ("Toledo",             "08", "Castilla-La Mancha"),
    "46": ("Valencia",           "10", "Comunitat Valenciana"),
    "47": ("Valladolid",         "07", "Castilla y León"),
    "48": ("Bizkaia",            "16", "País Vasco"),
    "49": ("Zamora",             "07", "Castilla y León"),
    "50": ("Zaragoza",           "02", "Aragón"),
    "51": ("Ceuta",              "18", "Ceuta"),
    "52": ("Melilla",            "19", "Melilla"),
}

# URLs de descarga del catálogo INE (de más reciente a más antigua)
# A partir de 2025 el INE cambió el patrón: YYcodmun.xlsx / diccionarioYY.xlsx
INE_CATALOG_URLS = [
    "https://www.ine.es/daco/daco42/codmun/diccionario26.xlsx",
    "https://www.ine.es/daco/daco42/codmun/26codmun.xlsx",
    "https://www.ine.es/daco/daco42/codmun/diccionario25.xlsx",
    "https://www.ine.es/daco/daco42/codmun/25codmun.xlsx",
    "https://www.ine.es/daco/daco42/codmun/codmun24.xlsx",
    "https://www.ine.es/daco/daco42/codmun/codmun23.xlsx",
]


@dataclass
class MunicipalityRecord:
    ine_code: str          # 5 dígitos: CPRO(2) + CMUN(3)
    name: str
    province_code: str     # 2 dígitos
    province_name: str
    ccaa_code: str         # 2 dígitos
    ccaa_name: str


def _clean_name(val) -> str:
    """Limpia el nombre del municipio: elimina espacios extra y caracteres raros."""
    if val is None:
        return ""
    return str(val).strip().replace("  ", " ")


def _parse_ine_xlsx(data: bytes) -> list[MunicipalityRecord]:
    """
    Parsea el XLSX del INE con el catálogo de municipios.
    El fichero tiene columnas: CPRO, CMUN, DC, NOMBRE
    (DC = dígito de control, no lo usamos)
    Intenta skiprows=1 y skiprows=0 para adaptarse a distintos formatos.
    """
    for skiprows in (1, 0):
        df = pd.read_excel(io.BytesIO(data), dtype=str, skiprows=skiprows)
        df.columns = [str(c).strip().upper() for c in df.columns]
        if "CPRO" in df.columns and "CMUN" in df.columns:
            break
    else:
        raise ValueError(f"Formato XLSX del INE no reconocido. Columnas: {list(df.columns)}")

    records: list[MunicipalityRecord] = []

    for _, row in df.iterrows():
        cpro = str(row.get("CPRO", "")).strip().zfill(2)
        cmun = str(row.get("CMUN", "")).strip().zfill(3)
        name = _clean_name(row.get("NOMBRE"))

        if not cpro or not cmun or not name or cpro == "nan":
            continue

        # Solo municipios de España peninsular, islas y ciudades autónomas
        if not re.match(r"^\d{2}$", cpro):
            continue

        ine_code = cpro + cmun
        prov_info = PROVINCE_MAP.get(cpro)
        if not prov_info:
            continue

        prov_name, ccaa_code, ccaa_name = prov_info

        records.append(MunicipalityRecord(
            ine_code=ine_code,
            name=name,
            province_code=cpro,
            province_name=prov_name,
            ccaa_code=ccaa_code,
            ccaa_name=ccaa_name,
        ))

    logger.info("ine_catalog_parsed", count=len(records))
    return records


async def download_ine_catalog() -> list[MunicipalityRecord]:
    """Descarga el catálogo INE. Prueba varias URLs por si la más reciente falla."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for url in INE_CATALOG_URLS:
            try:
                logger.info("downloading_ine_catalog", url=url)
                resp = await client.get(url)
                resp.raise_for_status()
                return _parse_ine_xlsx(resp.content)
            except Exception as e:
                logger.warning("ine_catalog_url_failed", url=url, error=str(e))
                continue
    raise RuntimeError("No se pudo descargar el catálogo INE de ninguna URL")


def load_ine_catalog_from_file(path: Path) -> list[MunicipalityRecord]:
    """Alternativa: carga desde fichero local (útil en dev sin red)."""
    with open(path, "rb") as f:
        return _parse_ine_xlsx(f.read())


# ── Seeder de base de datos ──────────────────────────────────────────────────

async def seed_municipalities(db, records: list[MunicipalityRecord]) -> int:
    """
    Inserta o actualiza el catálogo de municipios en la BD.
    Usa upsert por ine_code para ser idempotente.
    Retorna el número de registros procesados.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from models.national import Municipality

    if not records:
        return 0

    batch = [
        {
            "ine_code":      r.ine_code,
            "name":          r.name,
            "province_code": r.province_code,
            "province_name": r.province_name,
            "ccaa_code":     r.ccaa_code,
            "ccaa_name":     r.ccaa_name,
        }
        for r in records
    ]

    # Upsert por lotes de 500
    BATCH = 500
    total = 0
    for i in range(0, len(batch), BATCH):
        chunk = batch[i:i + BATCH]
        stmt = pg_insert(Municipality).values(chunk).on_conflict_do_update(
            index_elements=["ine_code"],
            set_={
                "name":          pg_insert(Municipality).excluded.name,
                "province_name": pg_insert(Municipality).excluded.province_name,
                "ccaa_name":     pg_insert(Municipality).excluded.ccaa_name,
            }
        )
        await db.execute(stmt)
        total += len(chunk)

    logger.info("municipalities_seeded", total=total)
    return total

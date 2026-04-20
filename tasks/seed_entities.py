"""
Tarea Celery: puebla municipal_entities con el árbol de entidades del municipio.

Estrategia genérica (no hardcodeada):
  1. Llama a rendiciondecuentas.es buscando entidades asociadas al municipio
     por su id_entidad principal (configurado en CITY_ID_ENTIDAD).
  2. Infiere el tipo (ayto/opa/empresa/fundacion/consorcio) de la categoría IGAE.
  3. Crea el NIF sintético del grupo consolidado: G{ine_code}0.
  4. Si la búsqueda falla (red, cambio de API), siembra al menos el ayuntamiento
     principal con los datos de CITY_NIF y CITY_NAME.

Uso manual (Celery):
    docker exec citydashboard_worker celery -A tasks.celery_app call \
        tasks.seed_entities.seed_municipal_entities

Uso en código (solo en tests o scripts de mantenimiento):
    from tasks.seed_entities import seed_municipal_entities
    seed_municipal_entities.delay()
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests
import structlog
from bs4 import BeautifulSoup

from tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)

_BASE_RC = "https://www.rendiciondecuentas.es"

# Mapa: categoría IGAE (texto) → tipo normalizado de entidad
_TIPO_MAP: dict[str, str] = {
    "ayuntamiento":           "ayto",
    "municipio":              "ayto",
    "organismo autónomo":     "opa",
    "organismo autónomo local": "opa",
    "ente público":           "opa",
    "entidad pública":        "opa",
    "empresa":                "empresa",
    "sociedad":               "empresa",
    "mercantil":              "empresa",
    "fundación":              "fundacion",
    "consorcio":              "consorcio",
    "mancomunidad":           "consorcio",
}


def _infer_tipo(categoria: str) -> str:
    """Devuelve el tipo normalizado a partir de la categoría IGAE en texto libre."""
    low = (categoria or "").lower()
    for key, tipo in _TIPO_MAP.items():
        if key in low:
            return tipo
    return "empresa"  # fallback conservador


def _discover_entities_rendicion(id_entidad_ppal: int) -> list[dict]:
    """
    Intenta descubrir las entidades dependientes del municipio en rendiciondecuentas.es.

    Devuelve lista de dicts con claves: nif, nombre, nombre_corto, tipo, id_rendicion.
    Devuelve [] si la API no responde o no tiene el formato esperado.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "CityDashboardBot/1.0 (civic-tech)"

    try:
        # Página de relación de entidades del grupo municipal
        # El portal lista entidades dependientes en la ficha de la entidad principal
        url = f"{_BASE_RC}/servlets/VerFichaEntidadServlet?id_entidad={id_entidad_ppal}"
        resp = session.get(url, timeout=20)
        if not resp.ok:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        entities = []
        # Buscar tabla de entidades dependientes
        for row in soup.select("table.tablaBusqueda tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            link = row.find("a", href=True)
            if not link:
                continue

            # Extraer id_entidad del href: VerFichaEntidadServlet?id_entidad=XXXX
            href = link["href"]
            if "id_entidad=" not in href:
                continue
            try:
                dep_id = int(href.split("id_entidad=")[1].split("&")[0])
            except (IndexError, ValueError):
                continue

            nombre = link.get_text(strip=True)
            categoria = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            nif_text  = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            if not nif_text or len(nif_text) < 9:
                continue

            entities.append({
                "nif":         nif_text.strip().upper(),
                "nombre":      nombre,
                "nombre_corto": nombre[:60],
                "tipo":        _infer_tipo(categoria),
                "id_rendicion": dep_id,
            })

        return entities

    except Exception as exc:
        logger.warning("rendicion_entity_discovery_failed", error=str(exc))
        return []


def _run_seed(settings) -> dict:
    """Lógica de seed sincrónica (sin event loop). Devuelve resumen de resultados."""
    import asyncio
    from app.db import AsyncSessionLocal, engine
    from models.budget import MunicipalEntity
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    ine_code = settings.city_ine_code
    parent_nif = settings.city_nif

    # 1. Descubrir entidades dependientes
    discovered = _discover_entities_rendicion(settings.city_id_entidad)
    logger.info("entities_discovered", count=len(discovered))

    # 2. Construir lista definitiva de entidades a sembrar
    entities_to_seed = []

    # Ayuntamiento principal (siempre presente)
    entities_to_seed.append({
        "nif":          parent_nif,
        "nombre":       settings.city_name,
        "nombre_corto": settings.city_name[:60],
        "tipo":         "ayto",
        "parent_nif":   None,
        "ine_code":     ine_code,
        "id_rendicion": settings.city_id_entidad,
        "activo":       True,
        "alias_fuentes": None,
    })

    # Entidades dependientes descubiertas
    for ent in discovered:
        if ent["nif"] == parent_nif:
            continue
        entities_to_seed.append({
            "nif":          ent["nif"],
            "nombre":       ent["nombre"],
            "nombre_corto": ent["nombre_corto"],
            "tipo":         ent["tipo"],
            "parent_nif":   parent_nif,
            "ine_code":     ine_code,
            "id_rendicion": ent.get("id_rendicion"),
            "activo":       True,
            "alias_fuentes": None,
        })

    # Grupo consolidado (NIF sintético — nunca hardcodeado por ciudad)
    grupo_nif = f"G{ine_code}0"
    entities_to_seed.append({
        "nif":          grupo_nif,
        "nombre":       f"Grupo Municipal — {settings.city_name}",
        "nombre_corto": f"Grupo {ine_code}",
        "tipo":         "grupo",
        "parent_nif":   parent_nif,
        "ine_code":     ine_code,
        "id_rendicion": None,
        "activo":       True,
        "alias_fuentes": None,
    })

    # 3. Upsert en BD
    async def _upsert():
        async with AsyncSessionLocal() as db:
            for ent in entities_to_seed:
                stmt = (
                    pg_insert(MunicipalEntity)
                    .values(**ent)
                    .on_conflict_do_update(
                        index_elements=["nif"],
                        set_={
                            "nombre":       ent["nombre"],
                            "nombre_corto": ent["nombre_corto"],
                            "tipo":         ent["tipo"],
                            "ine_code":     ent["ine_code"],
                            "id_rendicion": ent["id_rendicion"],
                            "activo":       True,
                        },
                    )
                )
                await db.execute(stmt)
            await db.commit()
        await engine.dispose()

    asyncio.run(_upsert())

    return {
        "seeded":    len(entities_to_seed),
        "ine_code":  ine_code,
        "main_nif":  parent_nif,
        "grupo_nif": grupo_nif,
    }


@celery_app.task(
    bind=True,
    name="tasks.seed_entities.seed_municipal_entities",
    max_retries=1,
    soft_time_limit=120,
    time_limit=180,
    queue="etl",
)
def seed_municipal_entities(self) -> dict:
    """
    Puebla la tabla municipal_entities con el árbol de entidades del municipio.

    Usa CITY_INE_CODE y CITY_ID_ENTIDAD de la configuración para descubrir
    las entidades dependientes en rendiciondecuentas.es. Si la API no responde,
    siembra solo el ayuntamiento principal.

    Idempotente: upserta por NIF, no duplica.
    """
    from app.config import get_settings
    settings = get_settings()

    logger.info(
        "seed_entities_start",
        city=settings.city_name,
        ine_code=settings.city_ine_code,
        id_entidad=settings.city_id_entidad,
    )

    try:
        result = _run_seed(settings)
        logger.info("seed_entities_done", **result)
        return result
    except Exception as exc:
        logger.error("seed_entities_failed", error=str(exc))
        raise self.retry(exc=exc)

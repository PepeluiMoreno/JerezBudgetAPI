"""
Módulo de integración con OpenStreetMap.

Proporciona acceso a datos geográficos del municipio mediante:
  - Overpass API  → consultas de equipamientos, viales, POIs por área
  - Nominatim     → geocodificación y búsqueda de límites administrativos
  - OSM tiles     → URLs de teselas para Leaflet/MapLibre en el frontend

Uso típico:
    from services.osm import OverpassClient, get_city_boundary

    client = OverpassClient()
    hospitals = await client.query_amenity("hospital")
    boundary = await get_city_boundary()

Toda la configuración geográfica (relation ID, bbox, lat/lon) se lee de
settings — no hay valores Jerez-específicos en este módulo.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ── URLs de los servicios OSM ─────────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org"

# Cabecera User-Agent obligatoria para Nominatim (política de uso)
_UA_HEADER = "CityDashboard/1.0 (civic-tech; contact via github)"


# ── Cliente Overpass ──────────────────────────────────────────────────────────

class OverpassClient:
    """
    Cliente asíncrono para la Overpass API.

    Todas las queries se acotan automáticamente al área OSM de la ciudad
    configurada en settings, sin necesidad de especificar coordenadas.

    Ejemplo de uso:
        client = OverpassClient()

        # Hospitales dentro del municipio
        result = await client.query('''
            node["amenity"="hospital"](area.city);
            out body;
        ''')

        # O usando helpers predefinidos:
        parks = await client.query_amenity("park", element="way")
    """

    def __init__(self, timeout: int = 60) -> None:
        from app.config import get_settings
        self._s = get_settings()
        self._timeout = timeout

    def _wrap_area_query(self, inner_query: str) -> str:
        """
        Envuelve una query Overpass con el bloque de área del municipio.
        El usuario escribe la parte interna usando `area.city` como filtro.
        """
        area_id = self._s.city_overpass_area
        return f"""
[out:json][timeout:{self._timeout}];
area(id:{area_id})->.city;
(
  {inner_query.strip()}
);
out body;
>;
out skel qt;
"""

    async def query(self, overpass_ql: str, wrap_area: bool = True) -> dict[str, Any]:
        """
        Ejecuta una query Overpass y devuelve el JSON completo.

        Args:
            overpass_ql: Bloque QL interno (sin el área wrapper si wrap_area=True).
            wrap_area:   Si True, añade automáticamente el bloque de área de la ciudad.
        """
        ql = self._wrap_area_query(overpass_ql) if wrap_area else overpass_ql
        logger.debug("overpass_query", city=self._s.city_name, ql_len=len(ql))

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                OVERPASS_URL,
                data={"data": ql},
                headers={"User-Agent": _UA_HEADER},
            )
            resp.raise_for_status()
            result = resp.json()

        elements = result.get("elements", [])
        logger.info("overpass_result", city=self._s.city_name, elements=len(elements))
        return result

    async def query_amenity(
        self,
        amenity_value: str,
        element: str = "node|way|relation",
    ) -> list[dict[str, Any]]:
        """
        Consulta equipamientos por valor de la etiqueta `amenity`.

        Args:
            amenity_value: Valor OSM (hospital, school, library, …)
            element:       Tipos de elementos: node, way, relation, o combinados con |

        Returns:
            Lista de elementos OSM con sus tags y coordenadas.

        Ejemplo:
            await client.query_amenity("hospital")
            await client.query_amenity("school", element="way")
        """
        parts = [e.strip() for e in element.split("|")]
        inner_lines = "\n  ".join(
            f'{e}["amenity"="{amenity_value}"](area.city);' for e in parts
        )
        result = await self.query(inner_lines)
        return result.get("elements", [])

    async def query_tag(
        self,
        key: str,
        value: str,
        element: str = "node|way|relation",
    ) -> list[dict[str, Any]]:
        """
        Consulta elementos OSM por cualquier par clave=valor.

        Ejemplo:
            await client.query_tag("leisure", "park")
            await client.query_tag("highway", "primary", element="way")
        """
        parts = [e.strip() for e in element.split("|")]
        inner_lines = "\n  ".join(
            f'{e}["{key}"="{value}"](area.city);' for e in parts
        )
        result = await self.query(inner_lines)
        return result.get("elements", [])

    async def query_raw(self, full_ql: str) -> dict[str, Any]:
        """
        Ejecuta una query Overpass completa (sin modificar).
        Útil para queries avanzadas que ya incluyen su propio filtro de área.
        """
        return await self.query(full_ql, wrap_area=False)


# ── Nominatim ─────────────────────────────────────────────────────────────────

async def get_city_boundary() -> dict[str, Any]:
    """
    Descarga el GeoJSON del límite administrativo del municipio desde Nominatim.
    Útil para inicializar el polígono en el mapa del frontend o calcular
    si un punto está dentro del término municipal.

    Returns:
        GeoJSON FeatureCollection con el polígono del municipio.
    """
    from app.config import get_settings
    s = get_settings()

    url = f"{NOMINATIM_URL}/lookup"
    params = {
        "osm_type": "R",  # Relation
        "osm_id": s.city_osm_relation_id,
        "format": "geojson",
        "polygon_geojson": 1,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url, params=params,
            headers={"User-Agent": _UA_HEADER},
        )
        resp.raise_for_status()
        data = resp.json()

    logger.info(
        "nominatim_boundary_fetched",
        city=s.city_name,
        osm_relation=s.city_osm_relation_id,
    )
    return data


async def geocode(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Búsqueda de lugares por texto, acotada al bbox del municipio.

    Returns:
        Lista de resultados Nominatim con nombre, coordenadas y tipo.
    """
    from app.config import get_settings
    s = get_settings()

    params = {
        "q": query,
        "format": "jsonv2",
        "limit": limit,
        "viewbox": f"{s.city_bbox_min_lon},{s.city_bbox_max_lat},{s.city_bbox_max_lon},{s.city_bbox_min_lat}",
        "bounded": 1,
        "countrycodes": "es",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{NOMINATIM_URL}/search", params=params,
            headers={"User-Agent": _UA_HEADER},
        )
        resp.raise_for_status()
        return resp.json()


# ── Helpers de uso frecuente ──────────────────────────────────────────────────

async def get_city_districts() -> list[dict[str, Any]]:
    """
    Devuelve los distritos/barrios del municipio como elementos OSM.
    Busca relaciones con admin_level=9 (barrios) o admin_level=8 (distritos)
    dentro del municipio.
    """
    client = OverpassClient()
    result = await client.query_raw(f"""
[out:json][timeout:60];
area(id:{client._s.city_overpass_area})->.city;
(
  relation["boundary"="administrative"]["admin_level"~"^(8|9|10)$"](area.city);
);
out body;
>;
out skel qt;
""")
    return result.get("elements", [])


async def get_public_services(categories: Optional[list[str]] = None) -> dict[str, list]:
    """
    Devuelve equipamientos públicos del municipio agrupados por categoría.

    Args:
        categories: Lista de valores amenity a consultar.
                    Por defecto: hospital, school, library, fire_station,
                    police, townhall, social_facility, post_office.

    Returns:
        Dict {amenity_value: [elementos OSM]}
    """
    default_categories = [
        "hospital", "clinic", "school", "college", "university",
        "library", "fire_station", "police", "townhall",
        "social_facility", "post_office", "community_centre",
    ]
    targets = categories or default_categories
    client = OverpassClient()

    results: dict[str, list] = {}
    for amenity in targets:
        try:
            elements = await client.query_amenity(amenity, element="node|way")
            results[amenity] = elements
            logger.info(
                "public_service_fetched",
                amenity=amenity,
                count=len(elements),
            )
        except Exception as exc:
            logger.warning("public_service_fetch_failed", amenity=amenity, error=str(exc))
            results[amenity] = []

    return results

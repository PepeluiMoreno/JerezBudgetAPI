"""
Configuración del Dashboard Dash y cliente de la API babbage.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import httpx

# ── Configuración ────────────────────────────────────────────────────────────

BABBAGE_BASE    = os.getenv("BABBAGE_BASE_URL", "http://api:8015/api/3")
DASH_HOST       = os.getenv("DASH_HOST", "0.0.0.0")
DASH_PORT       = int(os.getenv("DASH_PORT", "8050"))
DASH_DEBUG      = os.getenv("DASH_DEBUG", "false").lower() == "true"
DASH_PREFIX     = os.getenv("DASH_URL_PREFIX", "")   # para embed en iframe
API_PUBLIC_URL  = os.getenv("API_PUBLIC_URL", "http://localhost:8015")

JEREZ_INE    = "11020"
JEREZ_NAME   = "Jerez de la Frontera"

# Colores institucionales
COLORS = {
    "jerez":       "#C45D1A",   # naranja quemado — Jerez siempre en este color
    "peers":       "#1A4C8C",   # azul — municipios pares
    "national":    "#6B7280",   # gris — media nacional
    "good":        "#059669",   # verde — buena ejecución
    "warn":        "#D97706",   # ámbar — ejecución media
    "bad":         "#DC2626",   # rojo — baja ejecución
    "bg":          "#F9FAFB",
    "surface":     "#FFFFFF",
    "border":      "#E5E7EB",
    "text":        "#111827",
    "text_muted":  "#6B7280",
}

# Años disponibles en el sistema
AVAILABLE_YEARS = list(range(2010, 2025))
JEREZ_YEARS     = list(range(2020, 2027))

# Grupos de comparación
PEER_GROUPS = {
    "andalucia-100k-250k": "Municipios andaluces similares (100k-250k hab.)",
    "provincia-cadiz":     "Provincia de Cádiz",
    "capitales-andalucia": "Capitales de provincia andaluzas",
    "nacional-100k-250k":  "Municipios españoles similares (100k-250k hab.)",
}

# Nombres de capítulos
CHAPTER_NAMES = {
    "1": "Cap.1 Personal",
    "2": "Cap.2 Bienes y servicios",
    "3": "Cap.3 Gastos financieros",
    "4": "Cap.4 Transf. corrientes",
    "6": "Cap.6 Inversiones reales",
    "7": "Cap.7 Transf. capital",
    "9": "Cap.9 Pasivos financieros",
}

AREA_NAMES = {
    "1": "Servicios públicos básicos",
    "2": "Protección y promoción social",
    "3": "Bienes públicos preferentes",
    "4": "Actuaciones económicas",
    "9": "Actuaciones generales",
}


# ── Cliente API babbage ───────────────────────────────────────────────────────

class BabbageClient:
    """Cliente HTTP para la API babbage de JerezBudget."""

    def __init__(self, base_url: str = BABBAGE_BASE):
        self.base = base_url.rstrip("/")
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def aggregate(
        self,
        cube: str,
        drilldown: Optional[str] = None,
        cut: Optional[str] = None,
        order: Optional[str] = None,
        page: int = 1,
        pagesize: int = 500,
        aggregates: Optional[str] = None,
    ) -> list[dict]:
        """Llama a /aggregate y devuelve las celdas."""
        params = {"page": page, "pagesize": pagesize}
        if drilldown:
            params["drilldown"] = drilldown
        if cut:
            params["cut"] = cut
        if order:
            params["order"] = order
        if aggregates:
            params["aggregates"] = aggregates

        try:
            resp = self._client.get(f"{self.base}/cubes/{cube}/aggregate", params=params)
            resp.raise_for_status()
            return resp.json().get("cells", [])
        except Exception as e:
            import structlog
            structlog.get_logger().warning("babbage_aggregate_error", cube=cube, error=str(e))
            return []

    def members(
        self,
        cube: str,
        dimension: str,
        cut: Optional[str] = None,
        pagesize: int = 500,
    ) -> list[dict]:
        """Llama a /members/{dimension}."""
        params = {"pagesize": pagesize}
        if cut:
            params["cut"] = cut
        try:
            resp = self._client.get(
                f"{self.base}/cubes/{cube}/members/{dimension}", params=params
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception:
            return []


@lru_cache(maxsize=1)
def get_client() -> BabbageClient:
    return BabbageClient()

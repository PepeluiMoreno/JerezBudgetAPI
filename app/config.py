"""
Configuración centralizada de la aplicación.
Usa pydantic-settings para validar y cargar variables de entorno.

Las variables CITY_* parametrizan qué municipio es el "municipio propio"
del dashboard. Cambiarlas en .env permite reutilizar el proyecto para
cualquier ciudad española sin tocar el código fuente.
"""
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Base de datos ────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://citydashboard:dev@localhost:5432/citydashboard_db"

    # Pool de conexiones
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_echo: bool = False  # True para ver SQL en dev

    # ── Redis / Celery ───────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO ────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "citydashboard-sources"
    minio_secure: bool = False

    # ── API ──────────────────────────────────────────────────────
    api_debug: bool = False
    api_secret_key: str = "dev-secret-key-change-in-production"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8015"]

    # ── OpenDataManager (ODM) ────────────────────────────────────
    odmgr_base_url: str = "http://odmgr_app:8000"
    odmgr_webhook_secret: str = "dev-odmgr-secret-change-in-production"

    # ── Scraping ─────────────────────────────────────────────────
    transparencia_base_url: str = "https://transparencia.jerez.es"
    scrape_interval_hours: int = 24
    http_user_agent: str = "CityDashboardBot/1.0 (civic-tech)"
    http_timeout: int = 30

    # ── Logging ──────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "console"  # console | json

    # ── Aplicación ───────────────────────────────────────────────
    app_name: str = "CityDashboard API"
    app_version: str = "0.2.0"

    # Años fiscales soportados
    supported_years: list[int] = list(range(2020, 2027))

    # ── Ciudad propia ────────────────────────────────────────────
    # Estos parámetros identifican el municipio "home" del dashboard.
    # Cambiarlos en .env adapta el proyecto a cualquier ciudad española.
    city_name: str = "Jerez de la Frontera"
    city_ine_code: str = "11020"          # 5 dígitos INE
    city_province_code: str = "11"        # 2 dígitos INE (Cádiz)
    city_ccaa_code: str = "01"            # 2 dígitos INE (Andalucía)
    city_ccaa_name: str = "Andalucía"
    city_surface_km2: float = 1188.0      # término municipal en km²

    # Credenciales rendiciondecuentas.es (Tribunal de Cuentas)
    city_nif: str = "P1102000E"
    city_id_entidad: int = 1779

    # Grupos de pares — rangos de población para la comparativa
    # (peer group A: mismo rango que Jerez 150k-250k)
    peer_pop_min: int = 150_000
    peer_pop_max: int = 250_000
    # Margen ±% para grupo de superficie (peer group B)
    peer_surface_margin_pct: float = 15.0

    # ── Datos geográficos (OpenStreetMap) ────────────────────────
    # Permiten consultar la API Overpass, mostrar mapas y obtener
    # capas de equipamientos, viales, distritos, etc. desde OSM.

    # OSM relation ID del límite administrativo del municipio
    # Usado para: descargar el polígono del término municipal,
    #   obtener distritos/barrios, query por área en Overpass.
    # Jerez: https://www.openstreetmap.org/relation/340744
    city_osm_relation_id: int = 340744

    # Centroide (WGS84) — punto de inicio para mapas y búsquedas de proximidad
    city_lat: float = 36.6864
    city_lon: float = -6.1378

    # Bounding box del término municipal (WGS84)
    # Formato: [min_lon, min_lat, max_lon, max_lat]
    # Usado en Overpass API, Nominatim bounded search y viewport inicial de mapas
    city_bbox_min_lon: float = -6.4100
    city_bbox_min_lat: float = 36.4200
    city_bbox_max_lon: float = -5.7800
    city_bbox_max_lat: float = 36.9500

    @property
    def city_bbox(self) -> tuple[float, float, float, float]:
        """(min_lon, min_lat, max_lon, max_lat) — formato estándar GeoJSON/Overpass."""
        return (
            self.city_bbox_min_lon,
            self.city_bbox_min_lat,
            self.city_bbox_max_lon,
            self.city_bbox_max_lat,
        )

    @property
    def city_overpass_area(self) -> str:
        """
        String listo para usar en queries Overpass API.
        Ejemplo de uso:
            area(id:{city_overpass_area})->.searchArea;
            node["amenity"="hospital"](area.searchArea);
        """
        # Las areas en Overpass = OSM relation ID + 3_600_000_000
        return str(3_600_000_000 + self.city_osm_relation_id)

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL debe ser una URL de PostgreSQL")
        return v


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuración — cacheado para evitar re-lecturas."""
    return Settings()

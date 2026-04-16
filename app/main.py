"""
Aplicación FastAPI — JerezBudget API.
Punto de entrada para Uvicorn.
"""
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import engine
from api.health import router as health_router
from api.admin import router as admin_router
from api.olap.router import router as olap_router
from api.webhooks import router as webhooks_router

try:
    from graphql.schema import create_graphql_router as _create_graphql_router
    _graphql_available = True
except Exception as _graphql_err:
    import logging
    logging.getLogger(__name__).warning(
        "GraphQL no disponible (dependencias incompatibles): %s", _graphql_err
    )
    _graphql_available = False

settings = get_settings()

# ── Logging estructurado ─────────────────────────────────────────────────────
logging.basicConfig(level=settings.log_level.upper())
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level.upper())
    ),
)
logger = structlog.get_logger()


# ── Lifecycle ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "JerezBudget API arrancando",
        version=settings.app_version,
        debug=settings.api_debug,
    )
    yield
    logger.info("JerezBudget API apagando")
    await engine.dispose()


# ── App factory ──────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "API GraphQL para el análisis del rigor presupuestario del "
            "Ayuntamiento de Jerez de la Frontera. "
            "Compatible con OpenBudgets / Fiscal Data Package."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        debug=settings.api_debug,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── Static files ──────────────────────────────────────────────────────────
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(olap_router)
    app.include_router(webhooks_router)

    # GraphQL — accesible en /graphql (con GraphiQL en modo dev)
    if _graphql_available:
        graphql_router = _create_graphql_router()
        app.include_router(graphql_router, prefix="/graphql")

    # ── Root ──────────────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({
            "app": settings.app_name,
            "version": settings.app_version,
            "graphql": "/graphql",
            "admin": "/admin",
            "olap": "/api/3/cubes/",
            "health": "/health",
            "docs": "/docs",
        })

    return app


app = create_app()

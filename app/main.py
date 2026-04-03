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

from app.config import get_settings
from app.db import engine
from api.health import router as health_router
from graphql.schema import create_graphql_router

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

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router)

    # GraphQL — accesible en /graphql (con GraphiQL en modo dev)
    graphql_router = create_graphql_router()
    app.include_router(graphql_router, prefix="/graphql")

    # ── Root ──────────────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({
            "app": settings.app_name,
            "version": settings.app_version,
            "graphql": "/graphql",
            "graphiql": "/graphql",
            "health": "/health",
            "docs": "/docs",
        })

    return app


app = create_app()

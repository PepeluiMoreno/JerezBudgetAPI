"""
Endpoints de salud y estado de la aplicación.
Útiles para Docker healthcheck, Traefik y monitorización.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


@router.get("")
async def health_check():
    """Health check básico — siempre responde 200 si el proceso está vivo."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/db")
async def db_health(db: AsyncSession = Depends(get_db)):
    """Verifica conectividad con PostgreSQL."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": "disconnected", "detail": str(e)}


@router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """
    Readiness probe: confirma que la app está lista para recibir tráfico.
    Comprueba DB y que existan las tablas principales.
    """
    try:
        await db.execute(text("SELECT COUNT(*) FROM fiscal_years"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "detail": str(e)}

#!/usr/bin/env python3
"""
Script de inicialización del catálogo de municipios.

Descarga el catálogo oficial del INE y lo carga en la base de datos.
Ejecutar UNA VEZ tras aplicar la migración 0002.

Uso:
    docker compose run --rm api python scripts/seed_municipalities.py
    # o directamente:
    python scripts/seed_municipalities.py
"""
import asyncio
import sys
from pathlib import Path

# Añadir el raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

logger = structlog.get_logger()


async def main():
    from app.db import AsyncSessionLocal
    from etl.ine.municipalities_catalog import (
        download_ine_catalog,
        seed_municipalities,
    )
    from services.peer_groups import rebuild_dynamic_peer_groups

    logger.info("=== Seed municipios INE ===")

    # 1. Descargar catálogo
    logger.info("step_1_download", msg="Descargando catálogo INE...")
    try:
        records = await download_ine_catalog()
        logger.info("catalog_downloaded", count=len(records))
    except Exception as e:
        logger.error("catalog_download_failed", error=str(e))
        logger.info("hint", msg="Descarga el XLSX manualmente de: "
                   "https://www.ine.es/daco/daco42/codmun/codmun24.xlsx "
                   "y pásalo con --file codmun24.xlsx")
        sys.exit(1)

    # 2. Cargar en BD
    logger.info("step_2_seed", msg="Cargando en PostgreSQL...")
    async with AsyncSessionLocal() as db:
        n = await seed_municipalities(db, records)
        await db.commit()
        logger.info("seed_done", municipalities=n)

    # 3. Verificar Jerez
    from sqlalchemy import select
    from models.national import Municipality
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Municipality).where(Municipality.ine_code == "11021")
        )
        jerez = result.scalar_one_or_none()
        if jerez:
            logger.info(
                "jerez_ok",
                name=jerez.name,
                province=jerez.province_name,
                ccaa=jerez.ccaa_name,
            )
        else:
            logger.warning("jerez_not_found",
                          msg="Jerez (11021) no encontrado en el catálogo — verificar")

    # 4. Calcular peer groups (sin población aún — se recalculará tras ETL INE)
    logger.info("step_4_peer_groups", msg="Inicializando peer groups...")
    async with AsyncSessionLocal() as db:
        # Sin población todavía, los grupos por rango quedarán vacíos
        # Se rellenarán tras el ETL de población INE
        stats = await rebuild_dynamic_peer_groups(db)
        await db.commit()
        logger.info("peer_groups_initialized", stats=stats)

    logger.info("=== Seed completado ===")
    logger.info("next_steps", msg=(
        "Ejecuta ahora: celery call tasks.conprel_tasks.seed_ine_population "
        "para cargar la serie histórica de población"
    ))


if __name__ == "__main__":
    asyncio.run(main())

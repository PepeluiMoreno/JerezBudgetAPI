"""
Resolvers — ETL management.

Expone las excepciones de validación del ETL (discrepancias entre fuentes)
y permite reconocerlas (marcarlas como revisadas) mediante una mutation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.socioeconomic import EtlValidationException


async def resolve_etl_exceptions(
    db: AsyncSession,
    nif: Optional[str] = None,
    ejercicio: Optional[int] = None,
    only_pending: bool = True,
) -> list[EtlValidationException]:
    """
    Devuelve las excepciones de validación del ETL.

    - nif: filtra por entidad (None = todas)
    - ejercicio: filtra por año (None = todos)
    - only_pending: si True (por defecto), devuelve sólo las no reconocidas
    """
    q = select(EtlValidationException).order_by(
        EtlValidationException.detected_at.desc()
    )
    if nif:
        q = q.where(EtlValidationException.nif_entidad == nif)
    if ejercicio:
        q = q.where(EtlValidationException.ejercicio == ejercicio)
    if only_pending:
        q = q.where(EtlValidationException.acknowledged_at.is_(None))

    rows = await db.execute(q)
    return rows.scalars().all()


async def resolve_acknowledge_etl_exception(
    db: AsyncSession,
    exception_id: int,
    notes: Optional[str] = None,
) -> EtlValidationException:
    """Marca una excepción como reconocida."""
    exc = await db.get(EtlValidationException, exception_id)
    if exc is None:
        raise ValueError(f"Excepción ETL {exception_id} no encontrada")
    exc.acknowledged_at = datetime.now(timezone.utc)
    exc.ack_notes = notes
    await db.flush()
    return exc

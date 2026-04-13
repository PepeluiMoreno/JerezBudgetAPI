"""
Servicio de grupos de pares.

Tras cada ingestión de catálogo INE o CONPREL, recalcula
qué municipios pertenecen a cada peer group dinámico.

Un grupo dinámico tiene criteria JSONB con campos:
  - pop_min / pop_max    → rango de población
  - ccaa_code            → filtro por CCAA
  - province_code        → filtro por provincia
  - ine_codes            → lista explícita (grupos estáticos)
"""
from __future__ import annotations

from typing import Optional
import structlog

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.national import Municipality, PeerGroup, PeerGroupMember

logger = structlog.get_logger(__name__)

# Código INE de Jerez — constante de referencia
JEREZ_INE = "11020"


async def rebuild_dynamic_peer_groups(db: AsyncSession) -> dict[str, int]:
    """
    Recalcula los miembros de todos los peer groups dinámicos.
    Retorna {slug: n_miembros}.
    """
    result = await db.execute(
        select(PeerGroup).where(PeerGroup.is_dynamic == True)
    )
    groups = result.scalars().all()

    stats: dict[str, int] = {}

    for group in groups:
        n = await _rebuild_group(db, group)
        stats[group.slug] = n
        logger.info("peer_group_rebuilt", slug=group.slug, members=n)

    return stats


async def _rebuild_group(db: AsyncSession, group: PeerGroup) -> int:
    """
    Recalcula los miembros de un grupo dinámico y persiste el resultado.
    """
    criteria = group.criteria or {}

    # Construir query de municipios que cumplen los criterios
    q = select(Municipality).where(Municipality.is_active == True)

    # Filtro por rango de población
    pop_min = criteria.get("pop_min")
    pop_max = criteria.get("pop_max")
    if pop_min:
        q = q.where(Municipality.population >= pop_min)
    if pop_max:
        q = q.where(Municipality.population <= pop_max)

    # Filtro por CCAA
    ccaa_code = criteria.get("ccaa_code")
    if ccaa_code:
        q = q.where(Municipality.ccaa_code == ccaa_code)

    # Filtro por provincia
    province_code = criteria.get("province_code")
    if province_code:
        q = q.where(Municipality.province_code == province_code)

    # Lista explícita de códigos INE
    ine_codes: Optional[list[str]] = criteria.get("ine_codes")
    if ine_codes:
        q = q.where(Municipality.ine_code.in_(ine_codes))

    muns = await db.execute(q)
    members = muns.scalars().all()

    # Borrar miembros actuales y reinsertar
    await db.execute(
        delete(PeerGroupMember).where(PeerGroupMember.peer_group_id == group.id)
    )

    for mun in members:
        db.add(PeerGroupMember(
            peer_group_id=group.id,
            municipality_id=mun.id,
        ))

    await db.flush()
    return len(members)


async def get_jerez_peer_group(
    db: AsyncSession,
    slug: str = "andalucia-100k-250k",
) -> list[Municipality]:
    """
    Devuelve los municipios del grupo de pares de Jerez.
    Útil para el dashboard y las queries de comparativa.
    """
    result = await db.execute(
        select(Municipality)
        .join(PeerGroupMember, PeerGroupMember.municipality_id == Municipality.id)
        .join(PeerGroup, PeerGroup.id == PeerGroupMember.peer_group_id)
        .where(PeerGroup.slug == slug)
        .order_by(Municipality.population.desc())
    )
    return list(result.scalars().all())


async def get_peer_group_ine_codes(
    db: AsyncSession,
    slug: str,
) -> list[str]:
    """Devuelve solo los códigos INE del grupo (para filtros SQL)."""
    muns = await get_jerez_peer_group(db, slug)
    return [m.ine_code for m in muns]


async def ensure_jerez_in_all_groups(db: AsyncSession) -> None:
    """
    Garantiza que Jerez (11020) esté en todos los peer groups
    donde debería estar por criterios. Se llama tras el seeding.
    """
    result = await db.execute(
        select(Municipality).where(Municipality.ine_code == JEREZ_INE)
    )
    jerez = result.scalar_one_or_none()
    if not jerez:
        logger.warning("jerez_not_found_in_municipalities")
        return

    logger.info(
        "jerez_found",
        name=jerez.name,
        population=jerez.population,
        ccaa=jerez.ccaa_name,
    )

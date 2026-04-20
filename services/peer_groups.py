"""
Servicio de grupos de pares.

Tras cada ingestión de catálogo INE o CONPREL, recalcula
qué municipios pertenecen a cada peer group dinámico.

Un grupo dinámico tiene criteria JSONB con campos:
  - pop_min / pop_max        → rango de población
  - surface_min / surface_max → rango de superficie en km²
  - ccaa_code                → filtro por CCAA
  - province_code            → filtro por provincia
  - ine_codes                → lista explícita (grupos estáticos)
"""
from __future__ import annotations

from typing import Optional
import structlog

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.national import Municipality, PeerGroup, PeerGroupMember

logger = structlog.get_logger(__name__)


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

    # Filtro por rango de superficie en km²
    surface_min = criteria.get("surface_min")
    surface_max = criteria.get("surface_max")
    if surface_min is not None:
        q = q.where(Municipality.superficie_km2 >= surface_min)
    if surface_max is not None:
        q = q.where(Municipality.superficie_km2 <= surface_max)

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


async def get_peer_group_municipalities(
    db: AsyncSession,
    slug: str,
) -> list[Municipality]:
    """
    Devuelve los municipios de un peer group ordenados por población desc.
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
    muns = await get_peer_group_municipalities(db, slug)
    return [m.ine_code for m in muns]


async def ensure_city_in_all_groups(db: AsyncSession) -> None:
    """
    Garantiza que el municipio propio (settings.city_ine_code) esté en todos
    los peer groups donde debería estar por criterios. Se llama tras el seeding.
    """
    from app.config import get_settings
    settings = get_settings()

    result = await db.execute(
        select(Municipality).where(Municipality.ine_code == settings.city_ine_code)
    )
    city = result.scalar_one_or_none()
    if not city:
        logger.warning("city_not_found_in_municipalities", ine_code=settings.city_ine_code)
        return

    logger.info(
        "city_found",
        name=city.name,
        population=city.population,
        ccaa=city.ccaa_name,
    )


def ensure_default_peer_groups_exist(criteria_list: list[dict]) -> list[dict]:
    """
    Genera las definiciones de los peer groups estándar a partir de la config.
    Retorna lista de dicts {slug, name, description, criteria, is_dynamic}.

    Se llama desde scripts/seed_peer_groups.py tras el seeding de municipios.
    """
    from app.config import get_settings
    s = get_settings()

    surface = s.city_surface_km2
    margin = surface * s.peer_surface_margin_pct / 100.0

    return [
        {
            "slug": "nacional-150k-250k",
            "name": f"España — {s.peer_pop_min // 1000}k–{s.peer_pop_max // 1000}k habitantes",
            "description": (
                f"Municipios españoles con población entre "
                f"{s.peer_pop_min:,} y {s.peer_pop_max:,} habitantes"
            ),
            "criteria": {"pop_min": s.peer_pop_min, "pop_max": s.peer_pop_max},
            "is_dynamic": True,
        },
        {
            "slug": f"ccaa-{s.city_ccaa_code}-150k-250k",
            "name": f"{s.city_ccaa_name} — {s.peer_pop_min // 1000}k–{s.peer_pop_max // 1000}k habitantes",
            "description": (
                f"Municipios de {s.city_ccaa_name} con población entre "
                f"{s.peer_pop_min:,} y {s.peer_pop_max:,} habitantes"
            ),
            "criteria": {
                "pop_min": s.peer_pop_min,
                "pop_max": s.peer_pop_max,
                "ccaa_code": s.city_ccaa_code,
            },
            "is_dynamic": True,
        },
        {
            "slug": "nacional-superficie-similar",
            "name": f"España — superficie similar a {s.city_name}",
            "description": (
                f"Municipios españoles con término municipal de "
                f"{surface - margin:.0f}–{surface + margin:.0f} km² "
                f"({s.city_name} ≈ {surface:.0f} km², ±{s.peer_surface_margin_pct:.0f}%)"
            ),
            "criteria": {
                "surface_min": round(surface - margin, 2),
                "surface_max": round(surface + margin, 2),
            },
            "is_dynamic": True,
        },
    ]

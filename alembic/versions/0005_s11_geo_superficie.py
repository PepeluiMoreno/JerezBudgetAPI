"""S11 — superficie_km2 + OSM geo fields on municipalities

Añade a la tabla municipalities:
  - superficie_km2    → superficie del término municipal en km² (INE Nomenclator)
  - osm_relation_id   → OSM relation ID del límite administrativo
  - lat / lon         → centroide WGS84

Estos campos permiten:
  1. Calcular el peer group B (superficie similar a la ciudad propia ±15%)
  2. Consultar la API Overpass con el área OSM correcta
  3. Mostrar capas geográficas en el frontend Vue con Leaflet/MapLibre

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── municipalities: superficie + OSM geo ─────────────────────────────────
    op.add_column(
        "municipalities",
        sa.Column(
            "superficie_km2",
            sa.Numeric(10, 2),
            nullable=True,
            comment="Superficie del término municipal en km² (INE Nomenclator)",
        ),
    )
    op.add_column(
        "municipalities",
        sa.Column(
            "osm_relation_id",
            sa.Integer(),
            nullable=True,
            comment="OSM relation ID del límite administrativo",
        ),
    )
    op.add_column(
        "municipalities",
        sa.Column(
            "lat",
            sa.Numeric(9, 6),
            nullable=True,
            comment="Latitud del centroide (WGS84)",
        ),
    )
    op.add_column(
        "municipalities",
        sa.Column(
            "lon",
            sa.Numeric(9, 6),
            nullable=True,
            comment="Longitud del centroide (WGS84)",
        ),
    )

    # Índice para búsquedas por osm_relation_id (Overpass, webhooks)
    op.create_index(
        "ix_municipalities_osm_relation_id",
        "municipalities",
        ["osm_relation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_municipalities_osm_relation_id", table_name="municipalities")
    op.drop_column("municipalities", "lon")
    op.drop_column("municipalities", "lat")
    op.drop_column("municipalities", "osm_relation_id")
    op.drop_column("municipalities", "superficie_km2")

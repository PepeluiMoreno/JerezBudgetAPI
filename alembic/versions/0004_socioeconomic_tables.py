"""Add socioeconomic tables for ODM integration

Tablas para datos socioeconómicos sincronizados desde OpenDataManager:
  - municipal_population  — padrón municipal INE (necesario para €/hab)
  - cuenta_general_kpis   — KPIs sostenibilidad de Cuenta General XBRL

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ine_padron_municipal ──────────────────────────────────────────────────
    # Tabla ODM para el Padrón Municipal INE con desglose por sexo y código INE.
    # Distinta de municipal_population (CONPREL, FK a municipalities, sin sexo).
    op.create_table(
        "ine_padron_municipal",
        sa.Column("id",               sa.Integer(),     primary_key=True),
        sa.Column("municipio_cod",    sa.String(10),    nullable=False),
        sa.Column("municipio_nombre", sa.String(200),   nullable=True),
        sa.Column("year",             sa.Integer(),     nullable=False),
        sa.Column("sexo_cod",         sa.String(5),     nullable=False, server_default="T"),
        sa.Column("sexo_nombre",      sa.String(20),    nullable=True),
        sa.Column("habitantes",       sa.Integer(),     nullable=True),
        sa.Column("odmgr_dataset_id", sa.String(36),    nullable=True),
        sa.Column("synced_at",        sa.DateTime(),    server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_ine_padron_municipio_year_sexo",
        "ine_padron_municipal",
        ["municipio_cod", "year", "sexo_cod"],
    )
    op.create_index("ix_ine_padron_municipio_year", "ine_padron_municipal",
                    ["municipio_cod", "year"])
    op.create_index("ix_ine_padron_year", "ine_padron_municipal", ["year"])

    # ── cuenta_general_kpis ──────────────────────────────────────────────────
    op.create_table(
        "cuenta_general_kpis",
        sa.Column("id",               sa.Integer(),     primary_key=True),
        sa.Column("nif_entidad",      sa.String(20),    nullable=False),
        sa.Column("ejercicio",        sa.Integer(),     nullable=False),
        sa.Column("kpi",              sa.String(80),    nullable=False),
        sa.Column("valor",            sa.Numeric(18, 2), nullable=True),
        sa.Column("unidad",           sa.String(10),    nullable=False, server_default="EUR"),
        sa.Column("fuente_cuenta",    sa.String(60),    nullable=True),
        sa.Column("odmgr_dataset_id", sa.String(36),    nullable=True),
        sa.Column("synced_at",        sa.DateTime(),    server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_cgkpi_entidad_ejercicio_kpi",
        "cuenta_general_kpis",
        ["nif_entidad", "ejercicio", "kpi"],
    )
    op.create_index("ix_cgkpi_ejercicio", "cuenta_general_kpis", ["ejercicio"])


def downgrade() -> None:
    op.drop_table("cuenta_general_kpis")
    op.drop_table("ine_padron_municipal")

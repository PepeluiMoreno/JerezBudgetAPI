"""S0: municipal_entities + periodo en cuenta_general_kpis

Añade la tabla municipal_entities (catálogo de entidades de la corporación
municipal, genérico para cualquier ciudad) y la columna periodo en
cuenta_general_kpis para soportar granularidad mensual y trimestral.

La migración es retrocompatible: todas las filas existentes quedan con
periodo='' (anual), y el unique constraint se amplía para incluir periodo.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Tabla municipal_entities ───────────────────────────────────────────
    op.create_table(
        "municipal_entities",
        sa.Column("nif",          sa.String(20),  primary_key=True,
                  comment="NIF real (P...) o sintético G{ine_code}0 para grupo"),
        sa.Column("nombre",       sa.String(300), nullable=False),
        sa.Column("nombre_corto", sa.String(60),  nullable=False),
        sa.Column("tipo",         sa.String(20),  nullable=False,
                  comment="ayto | opa | empresa | fundacion | consorcio | grupo"),
        sa.Column("parent_nif",   sa.String(20),  nullable=True),
        sa.Column("ine_code",     sa.String(10),  nullable=False,
                  comment="Código INE del municipio (5 dígitos)"),
        sa.Column("id_rendicion", sa.Integer(),   nullable=True,
                  comment="ID en rendiciondecuentas.es"),
        sa.Column("activo",       sa.Boolean(),   nullable=False, server_default="true"),
        sa.Column("alias_fuentes", sa.Text(),     nullable=True,
                  comment='JSON: {"pmp_pdf": "nombre en PDF", ...}'),
        sa.Column("created_at",   sa.DateTime(),  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",   sa.DateTime(),  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_municipal_entities_ine_code",   "municipal_entities", ["ine_code"])
    op.create_index("ix_municipal_entities_parent_nif", "municipal_entities", ["parent_nif"])
    op.create_foreign_key(
        "fk_municipal_entities_parent_nif",
        "municipal_entities", "municipal_entities",
        ["parent_nif"], ["nif"],
        ondelete="SET NULL",
    )

    # ── 2. Columna periodo en cuenta_general_kpis ─────────────────────────────
    op.add_column(
        "cuenta_general_kpis",
        sa.Column(
            "periodo",
            sa.String(7),
            nullable=False,
            server_default="",
            comment=(
                "Granularidad: '' anual | '01'-'12' mensual | 'T1'-'T4' trimestral"
            ),
        ),
    )

    # Rellenar filas existentes (server_default ya lo hace, pero por seguridad)
    op.execute("UPDATE cuenta_general_kpis SET periodo = '' WHERE periodo IS NULL")

    # ── 3. Ampliar unique constraint ──────────────────────────────────────────
    op.drop_constraint(
        "uq_cgkpi_entidad_ejercicio_kpi",
        "cuenta_general_kpis",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_cgkpi_entidad_ejercicio_kpi_periodo",
        "cuenta_general_kpis",
        ["nif_entidad", "ejercicio", "kpi", "periodo"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_cgkpi_entidad_ejercicio_kpi_periodo",
        "cuenta_general_kpis",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_cgkpi_entidad_ejercicio_kpi",
        "cuenta_general_kpis",
        ["nif_entidad", "ejercicio", "kpi"],
    )
    op.drop_column("cuenta_general_kpis", "periodo")

    op.drop_index("ix_municipal_entities_parent_nif", table_name="municipal_entities")
    op.drop_index("ix_municipal_entities_ine_code",   table_name="municipal_entities")
    op.drop_table("municipal_entities")

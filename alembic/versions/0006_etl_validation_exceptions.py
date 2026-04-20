"""ETL validation exceptions — log de discrepancias entre fuentes de datos

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "etl_validation_exceptions",
        sa.Column("id",               sa.Integer(),     primary_key=True),
        sa.Column("nif_entidad",      sa.String(20),    nullable=False),
        sa.Column("ejercicio",        sa.Integer(),     nullable=False),
        sa.Column("kpi",              sa.String(80),    nullable=False),
        sa.Column("fuente_existente", sa.String(100),   nullable=True),
        sa.Column("valor_existente",  sa.Numeric(18, 2),nullable=True),
        sa.Column("fuente_nueva",     sa.String(100),   nullable=True),
        sa.Column("valor_nuevo",      sa.Numeric(18, 2),nullable=True),
        sa.Column("diff_pct",         sa.Float(),       nullable=True,
                  comment="Diferencia relativa en %. Positivo = nuevo > existente."),
        sa.Column("diff_abs",         sa.Numeric(18, 2),nullable=True,
                  comment="Diferencia absoluta: valor_nuevo - valor_existente"),
        sa.Column("accion",           sa.String(20),    nullable=False,
                  server_default="pending",
                  comment="kept_existing | updated | pending"),
        sa.Column("detected_at",      sa.DateTime(),    server_default=sa.func.now()),
        sa.Column("acknowledged_at",  sa.DateTime(),    nullable=True),
        sa.Column("ack_notes",        sa.Text(),        nullable=True),
    )
    op.create_index("ix_etlexc_nif_ejercicio",  "etl_validation_exceptions",
                    ["nif_entidad", "ejercicio"])
    op.create_index("ix_etlexc_acknowledged",   "etl_validation_exceptions",
                    ["acknowledged_at"])


def downgrade() -> None:
    op.drop_index("ix_etlexc_acknowledged",  table_name="etl_validation_exceptions")
    op.drop_index("ix_etlexc_nif_ejercicio", table_name="etl_validation_exceptions")
    op.drop_table("etl_validation_exceptions")

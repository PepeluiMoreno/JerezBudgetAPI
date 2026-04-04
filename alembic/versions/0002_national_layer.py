"""National comparison layer — Sprint 04

Crea las tablas de la Capa 2 (comparativa nacional):
  - municipalities
  - municipal_population
  - municipal_budgets
  - municipal_budget_chapters
  - municipal_budget_programs
  - peer_groups
  - peer_group_members

Y la vista materializada mv_comparison_jerez para el dashboard.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── municipalities ────────────────────────────────────────────────────────
    op.create_table(
        "municipalities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ine_code", sa.String(5), nullable=False,
                  comment="Código INE 5 dígitos: '11021' = Jerez"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("province_code", sa.String(2), nullable=False),
        sa.Column("province_name", sa.Text(), nullable=False),
        sa.Column("ccaa_code", sa.String(2), nullable=False),
        sa.Column("ccaa_name", sa.Text(), nullable=False),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("population_year", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_municipalities_ine_code", "municipalities", ["ine_code"], unique=True)
    op.create_index("ix_municipalities_province_code", "municipalities", ["province_code"])
    op.create_index("ix_municipalities_ccaa_code", "municipalities", ["ccaa_code"])

    # ── municipal_population ──────────────────────────────────────────────────
    op.create_table(
        "municipal_population",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("municipality_id", sa.Integer(),
                  sa.ForeignKey("municipalities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="INE_PADRON"),
        sa.UniqueConstraint("municipality_id", "year", name="uq_mun_pop_year"),
    )
    op.create_index("ix_municipal_population_mun_id", "municipal_population", ["municipality_id"])

    # ── municipal_budgets ─────────────────────────────────────────────────────
    op.create_table(
        "municipal_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("municipality_id", sa.Integer(),
                  sa.ForeignKey("municipalities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("data_type", sa.String(15), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("conprel_year", sa.Integer(), nullable=True),
        sa.Column("is_extension", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_url", sa.Text(), nullable=True),
        # Totales
        sa.Column("total_expense_initial",  sa.Numeric(16, 2), nullable=True),
        sa.Column("total_expense_final",    sa.Numeric(16, 2), nullable=True),
        sa.Column("total_expense_executed", sa.Numeric(16, 2), nullable=True),
        sa.Column("total_revenue_initial",  sa.Numeric(16, 2), nullable=True),
        sa.Column("total_revenue_executed", sa.Numeric(16, 2), nullable=True),
        # Per-cápita
        sa.Column("expense_executed_per_capita", sa.Numeric(10, 2), nullable=True),
        sa.Column("revenue_executed_per_capita", sa.Numeric(10, 2), nullable=True),
        # Tasas
        sa.Column("expense_execution_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("revenue_execution_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("modification_rate",      sa.Numeric(6, 4), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "municipality_id", "fiscal_year", "data_type",
            name="uq_mun_budget_year_type"
        ),
        sa.CheckConstraint(
            "data_type IN ('budget', 'liquidation')",
            name="ck_mun_budget_data_type"
        ),
    )
    op.create_index("ix_municipal_budgets_mun_id",   "municipal_budgets", ["municipality_id"])
    op.create_index("ix_municipal_budgets_year",      "municipal_budgets", ["fiscal_year"])
    op.create_index("ix_municipal_budgets_year_type", "municipal_budgets", ["fiscal_year", "data_type"])

    # ── municipal_budget_chapters ─────────────────────────────────────────────
    op.create_table(
        "municipal_budget_chapters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("municipal_budget_id", sa.Integer(),
                  sa.ForeignKey("municipal_budgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter",   sa.String(1),  nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("initial_amount",  sa.Numeric(16, 2), nullable=True),
        sa.Column("final_amount",    sa.Numeric(16, 2), nullable=True),
        sa.Column("executed_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("initial_per_capita",  sa.Numeric(10, 2), nullable=True),
        sa.Column("executed_per_capita", sa.Numeric(10, 2), nullable=True),
        sa.Column("execution_rate",   sa.Numeric(6, 4), nullable=True),
        sa.Column("modification_rate", sa.Numeric(6, 4), nullable=True),
        sa.UniqueConstraint(
            "municipal_budget_id", "chapter", "direction",
            name="uq_mbc_chapter_dir"
        ),
        sa.CheckConstraint(
            "direction IN ('expense', 'revenue')",
            name="ck_mbc_direction"
        ),
    )
    op.create_index(
        "ix_mbc_budget_chapter_dir", "municipal_budget_chapters",
        ["municipal_budget_id", "chapter", "direction"]
    )
    op.create_index("ix_mbc_budget_id", "municipal_budget_chapters", ["municipal_budget_id"])

    # ── municipal_budget_programs ─────────────────────────────────────────────
    op.create_table(
        "municipal_budget_programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("municipal_budget_id", sa.Integer(),
                  sa.ForeignKey("municipal_budgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area_code", sa.String(1), nullable=False),
        sa.Column("area_name", sa.Text(), nullable=True),
        sa.Column("initial_amount",      sa.Numeric(16, 2), nullable=True),
        sa.Column("executed_amount",     sa.Numeric(16, 2), nullable=True),
        sa.Column("initial_per_capita",  sa.Numeric(10, 2), nullable=True),
        sa.Column("executed_per_capita", sa.Numeric(10, 2), nullable=True),
        sa.Column("execution_rate",      sa.Numeric(6, 4), nullable=True),
        sa.UniqueConstraint(
            "municipal_budget_id", "area_code",
            name="uq_mbp_budget_area"
        ),
    )
    op.create_index("ix_mbp_budget_id", "municipal_budget_programs", ["municipal_budget_id"])

    # ── peer_groups ───────────────────────────────────────────────────────────
    op.create_table(
        "peer_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("criteria", postgresql.JSONB(), nullable=True),
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_peer_groups_slug", "peer_groups", ["slug"], unique=True)

    # ── peer_group_members ────────────────────────────────────────────────────
    op.create_table(
        "peer_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("peer_group_id", sa.Integer(),
                  sa.ForeignKey("peer_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("municipality_id", sa.Integer(),
                  sa.ForeignKey("municipalities.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint(
            "peer_group_id", "municipality_id",
            name="uq_pgm_group_mun"
        ),
    )
    op.create_index("ix_pgm_peer_group_id",   "peer_group_members", ["peer_group_id"])
    op.create_index("ix_pgm_municipality_id", "peer_group_members", ["municipality_id"])

    # ── Vista materializada — comparativa Jerez vs pares ─────────────────────
    # Pre-agrega los datos de Jerez y su grupo de pares para el dashboard.
    # Se refresca con REFRESH MATERIALIZED VIEW CONCURRENTLY tras cada ingestión.
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_comparison_jerez AS
        SELECT
            m.ine_code,
            m.name                  AS municipality_name,
            m.province_name,
            m.ccaa_name,
            m.population,
            mb.fiscal_year,
            mb.data_type,
            mb.expense_execution_rate,
            mb.revenue_execution_rate,
            mb.modification_rate,
            mb.expense_executed_per_capita,
            mb.revenue_executed_per_capita,
            mbc.chapter,
            mbc.direction,
            mbc.initial_amount,
            mbc.executed_amount,
            mbc.initial_per_capita,
            mbc.executed_per_capita,
            mbc.execution_rate      AS chapter_execution_rate,
            mbc.modification_rate   AS chapter_modification_rate,
            -- Flag: ¿es Jerez?
            (m.ine_code = '11021')::boolean AS is_jerez,
            -- Flag: ¿está en el grupo de pares de Jerez (100k-250k, Andalucía)?
            EXISTS (
                SELECT 1 FROM peer_group_members pgm
                JOIN peer_groups pg ON pgm.peer_group_id = pg.id
                WHERE pgm.municipality_id = m.id
                  AND pg.slug = 'andalucia-100k-250k'
            ) AS is_peer_andalucia
        FROM municipalities m
        JOIN municipal_budgets mb ON mb.municipality_id = m.id
        JOIN municipal_budget_chapters mbc ON mbc.municipal_budget_id = mb.id
        WHERE
            -- Solo municipios con población > 10k (ruido estadístico)
            m.population > 10000
            AND mb.data_type = 'liquidation'
        WITH DATA
    """)

    # Índice único necesario para REFRESH CONCURRENTLY
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
            ix_mv_comparison_jerez_pk
        ON mv_comparison_jerez (ine_code, fiscal_year, chapter, direction)
    """)

    # Índices de consulta frecuente
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_cj_year
            ON mv_comparison_jerez (fiscal_year)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_cj_ine
            ON mv_comparison_jerez (ine_code)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mv_cj_peer
            ON mv_comparison_jerez (is_peer_andalucia, fiscal_year)
    """)

    # ── Datos iniciales: peer groups predefinidos ─────────────────────────────
    op.execute("""
        INSERT INTO peer_groups (slug, name, description, criteria, is_dynamic)
        VALUES
        (
            'andalucia-100k-250k',
            'Municipios andaluces 100k-250k habitantes',
            'Grupo de comparación principal: municipios de Andalucía con población '
            'entre 100.000 y 250.000 habitantes (rango Jerez)',
            '{"pop_min": 100000, "pop_max": 250000, "ccaa_code": "01"}',
            true
        ),
        (
            'provincia-cadiz',
            'Municipios de la provincia de Cádiz',
            'Todos los municipios de la provincia de Cádiz con datos disponibles',
            '{"province_code": "11"}',
            true
        ),
        (
            'capitales-andalucia',
            'Capitales de provincia andaluzas',
            'Las 8 capitales de provincia de Andalucía',
            '{"ine_codes": ["04013","11020","14021","18087","21041","23050","29067","41091"]}',
            false
        ),
        (
            'nacional-100k-250k',
            'Municipios españoles 100k-250k habitantes',
            'Todos los municipios de España con población entre 100k y 250k',
            '{"pop_min": 100000, "pop_max": 250000}',
            true
        )
        ON CONFLICT (slug) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_comparison_jerez")
    op.drop_table("peer_group_members")
    op.drop_table("peer_groups")
    op.drop_table("municipal_budget_programs")
    op.drop_table("municipal_budget_chapters")
    op.drop_table("municipal_budgets")
    op.drop_table("municipal_population")
    op.drop_table("municipalities")

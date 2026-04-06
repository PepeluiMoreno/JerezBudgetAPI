"""Add performance indexes for dashboard queries

Índices adicionales para las queries más frecuentes del dashboard Dash:
  - mv_comparison_jerez: índices ya creados en 0002
  - municipal_budgets: índice compuesto para ranking queries
  - municipal_budget_chapters: índices para drilldown OLAP
  - municipalities: índice de población para peer group queries

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-06
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Índice para ranking por €/hab — query más frecuente del dashboard
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mbc_executed_per_capita
        ON municipal_budget_chapters (executed_per_capita DESC)
        WHERE executed_per_capita IS NOT NULL
    """)

    # Índice para queries de evolución temporal por municipio
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mb_mun_year_type
        ON municipal_budgets (municipality_id, fiscal_year, data_type)
    """)

    # Índice de población para calcular peer groups dinámicos
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_municipalities_population
        ON municipalities (population)
        WHERE population IS NOT NULL AND is_active = true
    """)

    # Índice combinado para el scatter (execution_rate × modification_rate)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_mb_exec_mod_rates
        ON municipal_budgets (expense_execution_rate, modification_rate)
        WHERE expense_execution_rate IS NOT NULL
    """)

    # Índice para fiscal_years.is_extension — filtra prorrogas en el trend
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fy_year_extension
        ON fiscal_years (year, is_extension)
    """)

    # Índice para rigor_metrics por año — queries del gauge dashboard
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rigor_metrics_year_computed
        ON rigor_metrics (fiscal_year_id, computed_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mbc_executed_per_capita")
    op.execute("DROP INDEX IF EXISTS ix_mb_mun_year_type")
    op.execute("DROP INDEX IF EXISTS ix_municipalities_population")
    op.execute("DROP INDEX IF EXISTS ix_mb_exec_mod_rates")
    op.execute("DROP INDEX IF EXISTS ix_fy_year_extension")
    op.execute("DROP INDEX IF EXISTS ix_rigor_metrics_year_computed")

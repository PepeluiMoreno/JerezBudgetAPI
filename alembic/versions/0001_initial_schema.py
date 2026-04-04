"""Initial schema — Sprint 01/02

Crea todas las tablas del modelo de datos:
  - fiscal_years
  - economic_classifications
  - functional_classifications
  - organic_classifications
  - budget_snapshots
  - budget_lines
  - budget_modifications
  - rigor_metrics

Revision ID: 0001
Revises:
Create Date: 2026-04-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── fiscal_years ─────────────────────────────────────────────────────────
    op.create_table(
        "fiscal_years",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("is_extension", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("extended_from_year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("initial_budget_date", sa.Date(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("stability_report_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fiscal_years_year", "fiscal_years", ["year"], unique=True)

    # ── economic_classifications ──────────────────────────────────────────────
    op.create_table(
        "economic_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("chapter", sa.String(2), nullable=False),
        sa.Column("article", sa.String(2), nullable=True),
        sa.Column("concept", sa.String(5), nullable=True),
        sa.Column("subconcept", sa.String(10), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.CheckConstraint("direction IN ('expense', 'revenue')", name="ck_direction"),
    )
    op.create_index("ix_economic_classifications_code", "economic_classifications", ["code"], unique=True)
    op.create_index("ix_economic_classifications_chapter", "economic_classifications", ["chapter"])

    # ── functional_classifications ────────────────────────────────────────────
    op.create_table(
        "functional_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("area", sa.String(1), nullable=True),
        sa.Column("policy", sa.String(2), nullable=True),
        sa.Column("program_group", sa.String(3), nullable=True),
        sa.Column("program", sa.String(4), nullable=True),
        sa.Column("subprogram", sa.String(6), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_index("ix_functional_classifications_code", "functional_classifications", ["code"], unique=True)

    # ── organic_classifications ───────────────────────────────────────────────
    op.create_table(
        "organic_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("section", sa.String(2), nullable=True),
        sa.Column("service", sa.String(4), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_index("ix_organic_classifications_code", "organic_classifications", ["code"], unique=True)

    # ── budget_snapshots ──────────────────────────────────────────────────────
    op.create_table(
        "budget_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fiscal_year_id", sa.Integer(),
                  sa.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False, server_default="executed"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(64), nullable=True),
        sa.Column("minio_path", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("fiscal_year_id", "snapshot_date", "phase",
                            name="uq_snapshot_year_date_phase"),
    )
    op.create_index("ix_budget_snapshots_fiscal_year_id", "budget_snapshots", ["fiscal_year_id"])

    # ── budget_lines ──────────────────────────────────────────────────────────
    op.create_table(
        "budget_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(),
                  sa.ForeignKey("budget_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organic_id", sa.Integer(),
                  sa.ForeignKey("organic_classifications.id"), nullable=True),
        sa.Column("functional_id", sa.Integer(),
                  sa.ForeignKey("functional_classifications.id"), nullable=True),
        sa.Column("economic_id", sa.Integer(),
                  sa.ForeignKey("economic_classifications.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # Gastos
        sa.Column("initial_credits", sa.Numeric(16, 2), nullable=True),
        sa.Column("modifications", sa.Numeric(16, 2), nullable=True),
        sa.Column("final_credits", sa.Numeric(16, 2), nullable=True),
        sa.Column("commitments", sa.Numeric(16, 2), nullable=True),
        sa.Column("recognized_obligations", sa.Numeric(16, 2), nullable=True),
        sa.Column("payments_made", sa.Numeric(16, 2), nullable=True),
        sa.Column("pending_payment", sa.Numeric(16, 2), nullable=True),
        # Ingresos
        sa.Column("initial_forecast", sa.Numeric(16, 2), nullable=True),
        sa.Column("final_forecast", sa.Numeric(16, 2), nullable=True),
        sa.Column("recognized_rights", sa.Numeric(16, 2), nullable=True),
        sa.Column("net_collection", sa.Numeric(16, 2), nullable=True),
        sa.Column("pending_collection", sa.Numeric(16, 2), nullable=True),
    )
    op.create_index("ix_budget_lines_snapshot_id", "budget_lines", ["snapshot_id"])
    op.create_index("ix_bl_snapshot_economic", "budget_lines", ["snapshot_id", "economic_id"])
    op.create_index("ix_bl_snapshot_functional", "budget_lines", ["snapshot_id", "functional_id"])

    # ── budget_modifications ──────────────────────────────────────────────────
    op.create_table(
        "budget_modifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fiscal_year_id", sa.Integer(),
                  sa.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False),
        sa.Column("mod_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("resolution_date", sa.Date(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("fiscal_year_id", "ref", name="uq_modification_ref"),
        sa.CheckConstraint(
            "mod_type IN ('transfer','generate','carry_forward','supplementary','credit_reduction')",
            name="ck_mod_type",
        ),
        sa.CheckConstraint(
            "status IN ('approved','in_progress','rejected')",
            name="ck_mod_status",
        ),
    )
    op.create_index("ix_budget_modifications_fiscal_year_id", "budget_modifications", ["fiscal_year_id"])

    # ── rigor_metrics ─────────────────────────────────────────────────────────
    op.create_table(
        "rigor_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fiscal_year_id", sa.Integer(),
                  sa.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.Integer(),
                  sa.ForeignKey("budget_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expense_execution_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("revenue_execution_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("modification_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("num_modifications", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approval_delay_days", sa.Integer(), nullable=True),
        sa.Column("publication_delay_days", sa.Integer(), nullable=True),
        sa.Column("precision_index", sa.Numeric(5, 2), nullable=True),
        sa.Column("timeliness_index", sa.Numeric(5, 2), nullable=True),
        sa.Column("transparency_index", sa.Numeric(5, 2), nullable=True),
        sa.Column("global_rigor_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("by_chapter", postgresql.JSONB(), nullable=True),
        sa.Column("by_program", postgresql.JSONB(), nullable=True),
        sa.Column("by_section", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_rigor_metrics_fiscal_year_id", "rigor_metrics", ["fiscal_year_id"])


def downgrade() -> None:
    op.drop_table("rigor_metrics")
    op.drop_table("budget_modifications")
    op.drop_table("budget_lines")
    op.drop_table("budget_snapshots")
    op.drop_table("organic_classifications")
    op.drop_table("functional_classifications")
    op.drop_table("economic_classifications")
    op.drop_table("fiscal_years")

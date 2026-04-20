"""S0: kpi_thresholds + cesel_kpis

kpi_thresholds — umbrales de alerta para semáforos del cuadro de mando.
  Almacena límites legales (LOEPSF, Ley 15/2010) y de buena práctica
  junto con su base normativa, haciendo los semáforos auditables.

cesel_kpis — coste efectivo de servicios municipales (CESEL/Hacienda).
  Granularidad: anual × servicio × kpi.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. kpi_thresholds ────────────────────────────────────────────────────
    op.create_table(
        "kpi_thresholds",
        sa.Column("id",          sa.Integer(),      primary_key=True, autoincrement=True),
        sa.Column("kpi",         sa.String(80),     nullable=False,
                  comment="kpi_code al que aplica este umbral"),
        sa.Column("nivel",       sa.String(10),     nullable=False,
                  comment="'verde' | 'amarillo' | 'rojo'"),
        sa.Column("operador",    sa.String(2),      nullable=False,
                  comment="'<' | '>' | '<=' | '>='"),
        sa.Column("umbral",      sa.Numeric(18, 4), nullable=False),
        sa.Column("aplica_a",    sa.String(10),     nullable=False, server_default="todos",
                  comment="'ayto' | 'empresa' | 'todos'"),
        sa.Column("base_legal",  sa.String(200),    nullable=False, server_default=""),
        sa.Column("descripcion", sa.Text(),         nullable=False, server_default=""),
        sa.CheckConstraint("nivel IN ('verde', 'amarillo', 'rojo')",     name="ck_threshold_nivel"),
        sa.CheckConstraint("operador IN ('<', '>', '<=', '>=')",         name="ck_threshold_operador"),
        sa.CheckConstraint("aplica_a IN ('ayto', 'empresa', 'todos')",   name="ck_threshold_aplica"),
        sa.UniqueConstraint("kpi", "nivel", "aplica_a", name="uq_threshold_kpi_nivel_aplica"),
    )

    # Seed inicial: umbrales LOEPSF y Ley 15/2010
    _seed_thresholds()

    # ── 2. cesel_kpis ────────────────────────────────────────────────────────
    op.create_table(
        "cesel_kpis",
        sa.Column("id",          sa.Integer(),      primary_key=True, autoincrement=True),
        sa.Column("nif_entidad", sa.String(20),     nullable=False),
        sa.Column("ejercicio",   sa.Integer(),      nullable=False),
        sa.Column("servicio",    sa.String(200),    nullable=False,
                  comment="Código o descripción del servicio CESEL"),
        sa.Column("kpi",         sa.String(40),     nullable=False,
                  comment="'coste_total' | 'coste_por_usuario' | 'num_usuarios'"),
        sa.Column("valor",       sa.Numeric(18, 2), nullable=True),
        sa.Column("fuente",      sa.String(60),     nullable=False,
                  comment="'transparencia_cesel_xlsx'"),
        sa.Column("odmgr_dataset_id", sa.String(36), nullable=True),
        sa.Column("synced_at",   sa.DateTime(),     server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "nif_entidad", "ejercicio", "servicio", "kpi",
            name="uq_cesel_entidad_ejercicio_servicio_kpi",
        ),
    )
    op.create_index("ix_cesel_ejercicio",     "cesel_kpis", ["ejercicio"])
    op.create_index("ix_cesel_nif_ejercicio", "cesel_kpis", ["nif_entidad", "ejercicio"])


def _seed_thresholds() -> None:
    """Carga los umbrales legales y de buena práctica iniciales."""
    conn = op.get_bind()

    thresholds = [
        # PMP — Ley 15/2010 art. 5 (plazo máximo 30 días para administraciones locales)
        ("pmp_ayto",    "amarillo", ">",  30, "todos", "Ley 15/2010, art. 5",
         "PMP superior a 30 días: incumplimiento del plazo legal de pago"),
        ("pmp_ayto",    "rojo",     ">",  60, "todos", "Ley 15/2010, art. 5",
         "PMP superior a 60 días: incumplimiento grave, riesgo de sanciones"),

        # RTGG — LOEPSF art. 3 (sostenibilidad financiera)
        ("remanente_tesoreria_gastos_generales", "rojo", "<", 0, "ayto",
         "LOEPSF art. 3 + Instrucción de Contabilidad",
         "Remanente de tesorería negativo: posible déficit estructural"),

        # Deuda / ingresos corrientes — LOEPSF Disposición Adicional 14ª
        ("ratio_deuda_ingresos_corrientes", "amarillo", ">", 0.75, "ayto",
         "LOEPSF — umbrales de deuda",
         "Deuda > 75% de ingresos corrientes: zona de vigilancia"),
        ("ratio_deuda_ingresos_corrientes", "rojo",     ">", 1.10, "ayto",
         "LOEPSF art. 13 — límite de endeudamiento",
         "Deuda > 110% de ingresos corrientes: exceso de deuda, requiere plan de ajuste"),

        # Ejecución del gasto — buena práctica
        ("tasa_ejecucion_gasto", "amarillo", "<", 0.70, "ayto",
         "Buena práctica presupuestaria",
         "Ejecución del gasto inferior al 70%: infrautilización significativa del presupuesto"),
        ("tasa_ejecucion_gasto", "rojo",     "<", 0.50, "ayto",
         "Buena práctica presupuestaria",
         "Ejecución del gasto inferior al 50%: presupuesto ineficaz"),

        # Ratio pagos fuera de plazo — Ley 15/2010 + buena práctica
        ("ratio_pagos_fuera_plazo", "amarillo", ">", 0.20, "ayto",
         "Ley 15/2010 + buena práctica",
         "Más del 20% de pagos realizados fuera del plazo legal"),
        ("ratio_pagos_fuera_plazo", "rojo",     ">", 0.40, "ayto",
         "Ley 15/2010 + buena práctica",
         "Más del 40% de pagos fuera de plazo: riesgo de intereses de demora sistemáticos"),
    ]

    for row in thresholds:
        kpi, nivel, operador, umbral, aplica_a, base_legal, descripcion = row
        conn.execute(
            sa.text(
                "INSERT INTO kpi_thresholds "
                "(kpi, nivel, operador, umbral, aplica_a, base_legal, descripcion) "
                "VALUES (:kpi, :nivel, :op, :umbral, :aplica, :legal, :desc) "
                "ON CONFLICT (kpi, nivel, aplica_a) DO NOTHING"
            ),
            {
                "kpi":    kpi,
                "nivel":  nivel,
                "op":     operador,
                "umbral": umbral,
                "aplica": aplica_a,
                "legal":  base_legal,
                "desc":   descripcion,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_cesel_nif_ejercicio", table_name="cesel_kpis")
    op.drop_index("ix_cesel_ejercicio",     table_name="cesel_kpis")
    op.drop_table("cesel_kpis")
    op.drop_table("kpi_thresholds")

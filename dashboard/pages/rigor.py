"""
Vista 1 — Rigor presupuestario de Jerez de la Frontera.

Muestra:
  - Score Global de Rigor (gauge prominente)
  - IPP, ITP, ITR (tres gauges secundarios)
  - Serie histórica del score (línea 2020-2026)
  - Ejecución por capítulo económico (barras horizontales)
  - Panel de alertas (prórroga, baja ejecución, alta modificación)
"""
from __future__ import annotations

import dash
from dash import dcc, html, Input, Output, callback
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from dashboard.config import COLORS, CHAPTER_NAMES, JEREZ_INE, get_client
from dashboard.components import (
    kpi_card, score_gauge, year_dropdown, filter_bar,
    section_title, alert_box, empty_state, page_header,
)

dash.register_page(__name__, path="/rigor", name="Rigor presupuestario", order=0)


# ── Layout ────────────────────────────────────────────────────────────────────

layout = html.Div([

    page_header(
        "Rigor presupuestario — Jerez de la Frontera",
        "Índices IPP (Precisión), ITP (Puntualidad), ITR (Transparencia) · Fuente: transparencia.jerez.es"
    ),

    # Filtros
    filter_bar(
        html.Div(year_dropdown("rigor-year", years=list(range(2020, 2027)), value=2025),
                 style={"width": 140}),
    ),

    # Alertas dinámicas
    html.Div(id="rigor-alerts", style={"padding": "12px 28px 0"}),

    # KPIs superiores
    html.Div(id="rigor-kpis", style={
        "display": "grid",
        "gridTemplateColumns": "repeat(4, 1fr)",
        "gap": 12,
        "padding": "16px 28px",
    }),

    # Fila de gauges
    html.Div([
        html.Div([
            section_title("Score Global de Rigor"),
            html.Div(id="gauge-global", style={"textAlign": "center"}),
        ], style={"background": COLORS["surface"], "padding": 20, "flex": 1}),
        html.Div([
            section_title("Índices componentes"),
            html.Div([
                html.Div(id="gauge-ipp"),
                html.Div(id="gauge-itp"),
                html.Div(id="gauge-itr"),
            ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": 8}),
        ], style={"background": COLORS["surface"], "padding": 20, "flex": 2,
                  "marginLeft": 12}),
    ], style={
        "display": "flex", "padding": "0 28px 16px",
        "border": f"1px solid {COLORS['border']}",
        "margin": "0 28px 16px",
        "background": COLORS["surface"],
    }),

    # Fila inferior: histórico + ejecución por capítulo
    html.Div([
        html.Div([
            section_title("Evolución histórica del Score (2020-2026)"),
            dcc.Graph(id="rigor-trend-chart", config={"displayModeBar": False}),
        ], style={
            "background": COLORS["surface"],
            "border": f"1px solid {COLORS['border']}",
            "padding": 20, "flex": 1,
        }),
        html.Div([
            section_title("Ejecución por capítulo"),
            dcc.Graph(id="rigor-chapters-chart", config={"displayModeBar": False}),
        ], style={
            "background": COLORS["surface"],
            "border": f"1px solid {COLORS['border']}",
            "padding": 20, "flex": 1,
            "marginLeft": 12,
        }),
    ], style={"display": "flex", "padding": "0 28px 28px"}),

], style={"background": COLORS["bg"], "minHeight": "100vh", "fontFamily": "system-ui"})


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("rigor-alerts",         "children"),
    Output("rigor-kpis",           "children"),
    Output("gauge-global",         "children"),
    Output("gauge-ipp",            "children"),
    Output("gauge-itp",            "children"),
    Output("gauge-itr",            "children"),
    Output("rigor-trend-chart",    "figure"),
    Output("rigor-chapters-chart", "figure"),
    Input("rigor-year", "value"),
)
def update_rigor(year: int):
    client = get_client()

    # ── Métricas de rigor del año seleccionado ────────────────────────────────
    rigor_cells = client.aggregate(
        cube="jerez-rigor",
        drilldown="year.fiscal_year|year.is_extension",
        cut=f"year.fiscal_year:{year}",
    )

    score = ipp = itp = itr = None
    exp_rate = rev_rate = mod_rate = None
    is_extension = False
    delay_days = None

    if rigor_cells:
        r = rigor_cells[0]
        score    = _f(r, "global_rigor_score.avg")
        ipp      = _f(r, "precision_index.avg")
        itp      = _f(r, "timeliness_index.avg")
        itr      = _f(r, "transparency_index.avg")
        exp_rate = _f(r, "expense_execution_rate.avg")
        rev_rate = _f(r, "revenue_execution_rate.avg")
        mod_rate = _f(r, "modification_rate.avg")
        is_extension = str(r.get("year.is_extension", "false")).lower() == "true"

    # Días de retraso desde CONPREL (si disponible)
    rigor_dim = client.aggregate(
        cube="jerez-rigor",
        drilldown="year.fiscal_year|year.approval_delay_days",
        cut=f"year.fiscal_year:{year}",
    )
    if rigor_dim:
        delay_days = rigor_dim[0].get("year.approval_delay_days")

    # ── Alertas ───────────────────────────────────────────────────────────────
    alerts = []
    if is_extension:
        alerts.append(alert_box(
            f"⚠️  {year} es un presupuesto prorrogado del ejercicio anterior. "
            f"El Índice de Puntualidad (ITP) es 0 automáticamente.",
            "warning"
        ))
    if itp is not None and itp == 0 and not is_extension and delay_days:
        alerts.append(alert_box(
            f"⚠️  Retraso en la aprobación del presupuesto: {int(delay_days)} días "
            f"desde el 1 de enero.", "warning"
        ))
    if exp_rate is not None and exp_rate < 0.70:
        alerts.append(alert_box(
            f"🔴  Baja tasa de ejecución de gasto: {exp_rate:.1%}. "
            f"El presupuesto aprobado está significativamente por encima de lo ejecutado.",
            "error"
        ))
    if mod_rate is not None and mod_rate > 0.15:
        alerts.append(alert_box(
            f"📋  Alta tasa de modificaciones presupuestarias: {mod_rate:.1%}. "
            f"El presupuesto inicial puede estar sobredimensionado.",
            "warning"
        ))

    # ── KPI cards ─────────────────────────────────────────────────────────────
    def _pct(v):
        return f"{v:.1%}" if v is not None else "—"

    kpis = [
        kpi_card("Ejecución gasto",   _pct(exp_rate),
                 "Obligaciones / Créditos def.",
                 _exec_color(exp_rate)),
        kpi_card("Ejecución ingreso", _pct(rev_rate),
                 "Derechos / Previsiones def.",
                 _exec_color(rev_rate)),
        kpi_card("Tasa modificación", _pct(mod_rate),
                 "Variación sobre ppto. inicial",
                 COLORS["warn"] if mod_rate and mod_rate > 0.10 else COLORS["good"]),
        kpi_card("Retraso aprobación",
                 f"{int(delay_days)} días" if delay_days is not None else "—",
                 "Desde 1 de enero",
                 COLORS["bad"] if delay_days and delay_days > 30 else COLORS["good"]),
    ]

    # ── Gauges ────────────────────────────────────────────────────────────────
    g_global = score_gauge(score, "Score Global de Rigor", size=200)
    g_ipp    = score_gauge(ipp,   "IPP — Precisión",       size=140)
    g_itp    = score_gauge(itp,   "ITP — Puntualidad",     size=140)
    g_itr    = score_gauge(itr,   "ITR — Transparencia",   size=140)

    # ── Tendencia histórica ───────────────────────────────────────────────────
    trend_cells = client.aggregate(
        cube="jerez-rigor",
        drilldown="year.fiscal_year|year.is_extension",
        order="year.fiscal_year:asc",
        pagesize=20,
    )

    trend_fig = go.Figure()
    if trend_cells:
        years_t  = [r["year.fiscal_year"] for r in trend_cells]
        scores_t = [_f(r, "global_rigor_score.avg") for r in trend_cells]
        ipps     = [_f(r, "precision_index.avg") for r in trend_cells]
        itps_t   = [_f(r, "timeliness_index.avg") for r in trend_cells]
        is_ext   = [str(r.get("year.is_extension","false")).lower()=="true" for r in trend_cells]

        trend_fig.add_trace(go.Scatter(
            x=years_t, y=scores_t, name="Score Global",
            line={"color": COLORS["jerez"], "width": 3},
            mode="lines+markers",
            marker={"size": [12 if e else 8 for e in is_ext],
                    "symbol": ["diamond" if e else "circle" for e in is_ext],
                    "color": [COLORS["warn"] if e else COLORS["jerez"] for e in is_ext]},
        ))
        trend_fig.add_trace(go.Scatter(
            x=years_t, y=ipps, name="IPP Precisión",
            line={"color": COLORS["peers"], "width": 1.5, "dash": "dot"},
            mode="lines",
        ))
        trend_fig.add_trace(go.Scatter(
            x=years_t, y=itps_t, name="ITP Puntualidad",
            line={"color": COLORS["national"], "width": 1.5, "dash": "dash"},
            mode="lines",
        ))
        # Banda de referencia
        trend_fig.add_hrect(y0=75, y1=100, fillcolor=COLORS["good"],
                            opacity=0.06, line_width=0)
        trend_fig.add_hrect(y0=50, y1=75, fillcolor=COLORS["warn"],
                            opacity=0.06, line_width=0)

    _tl = _chart_layout(height=260)
    _tl["yaxis"].update({"range": [0, 105], "title": "Score (0-100)"})
    _tl["xaxis"].update({"dtick": 1})
    trend_fig.update_layout(
        **_tl,
        showlegend=True,
        legend={"orientation": "h", "y": -0.2, "font": {"size": 11}},
    )

    # ── Ejecución por capítulo ────────────────────────────────────────────────
    ch_cells = client.aggregate(
        cube="jerez-detail",
        drilldown="chapter.chapter|chapter.direction",
        cut=f"year.fiscal_year:{year}|chapter.direction:expense",
        order="chapter.chapter:asc",
        pagesize=20,
    )

    ch_fig = go.Figure()
    if ch_cells:
        chapters  = []
        ex_rates  = []
        colors_ch = []
        for r in ch_cells:
            ch = str(r.get("chapter.chapter", ""))
            if ch not in CHAPTER_NAMES:
                continue
            # Calcular tasa: obligations / final_credits
            obl = _f(r, "recognized_obligations.sum") or 0
            fin = _f(r, "final_credits.sum") or 1
            rate = obl / fin if fin > 0 else 0
            chapters.append(CHAPTER_NAMES.get(ch, f"Cap.{ch}"))
            ex_rates.append(round(rate * 100, 1))
            colors_ch.append(
                COLORS["good"] if rate >= 0.85
                else COLORS["warn"] if rate >= 0.70
                else COLORS["bad"]
            )

        ch_fig.add_trace(go.Bar(
            x=ex_rates, y=chapters,
            orientation="h",
            marker_color=colors_ch,
            text=[f"{v:.1f}%" for v in ex_rates],
            textposition="outside",
        ))
        ch_fig.add_vline(x=85, line_dash="dash",
                         line_color=COLORS["good"], line_width=1,
                         annotation_text="85% ref.", annotation_position="top")
    else:
        ch_fig.add_annotation(text="Sin datos de ejecución por capítulo",
                              showarrow=False, font={"color": COLORS["text_muted"]})

    _cl = _chart_layout(height=260)
    _cl["xaxis"].update({"range": [0, 120], "title": "Tasa de ejecución (%)"})
    ch_fig.update_layout(**_cl, showlegend=False)

    return alerts, kpis, g_global, g_ipp, g_itp, g_itr, trend_fig, ch_fig


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(row: dict, key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _exec_color(rate: float | None) -> str:
    if rate is None:
        return COLORS["text_muted"]
    if rate >= 0.85:
        return COLORS["good"]
    if rate >= 0.70:
        return COLORS["warn"]
    return COLORS["bad"]


def _chart_layout(height: int = 320) -> dict:
    return {
        "height": height,
        "margin": {"t": 10, "b": 40, "l": 10, "r": 20},
        "paper_bgcolor": COLORS["surface"],
        "plot_bgcolor": COLORS["bg"],
        "font": {"family": "system-ui", "size": 11, "color": COLORS["text"]},
        "xaxis": {"gridcolor": COLORS["border"]},
        "yaxis": {"gridcolor": COLORS["border"]},
    }

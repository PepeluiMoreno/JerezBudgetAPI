"""
Vista 2 — Comparativa entre ciudades.

Jerez vs municipios de su grupo de pares:
  - Ranking €/hab ejecutado (barras) con Jerez destacado
  - Scatter: tasa ejecución vs tasa modificación
  - Radar: 5 áreas funcionales Jerez vs media del grupo
  - Tabla de posición de Jerez en el ranking
"""
from __future__ import annotations

import dash
from dash import dcc, html, Input, Output, callback
import plotly.graph_objects as go
import pandas as pd

from dashboard.config import (
    COLORS, CHAPTER_NAMES, AREA_NAMES,
    JEREZ_INE, JEREZ_NAME, get_client,
)
from dashboard.components import (
    year_dropdown, peer_group_dropdown, chapter_dropdown,
    filter_bar, section_title, empty_state, page_header, kpi_card,
)

dash.register_page(__name__, path="/comparativa", name="Comparativa entre ciudades", order=1)


layout = html.Div([

    page_header(
        "Comparativa entre ciudades",
        "Jerez vs municipios similares · Fuente: CONPREL — Ministerio de Hacienda"
    ),

    filter_bar(
        html.Div(year_dropdown("cmp-year", value=2023), style={"width": 140}),
        html.Div(peer_group_dropdown("cmp-peer-group"), style={"width": 320}),
        html.Div(chapter_dropdown("cmp-chapter"), style={"width": 220}),
    ),

    # KPIs de posición de Jerez
    html.Div(id="cmp-position-kpis", style={
        "display": "grid", "gridTemplateColumns": "repeat(4, 1fr)",
        "gap": 12, "padding": "16px 28px 0",
    }),

    # Ranking + Scatter
    html.Div([
        html.Div([
            section_title("Ranking €/hab ejecutado"),
            dcc.Graph(id="cmp-ranking-chart", config={"displayModeBar": False}),
        ], style={"background": COLORS["surface"],
                  "border": f"1px solid {COLORS['border']}",
                  "padding": 20, "flex": 3}),
        html.Div([
            section_title("Ejecución vs Modificación"),
            dcc.Graph(id="cmp-scatter-chart", config={"displayModeBar": False}),
        ], style={"background": COLORS["surface"],
                  "border": f"1px solid {COLORS['border']}",
                  "padding": 20, "flex": 2, "marginLeft": 12}),
    ], style={"display": "flex", "padding": "16px 28px 12px"}),

    # Radar funcional
    html.Div([
        html.Div([
            section_title("Áreas funcionales: Jerez vs media del grupo (€/hab)"),
            dcc.Graph(id="cmp-radar-chart", config={"displayModeBar": False}),
        ], style={"background": COLORS["surface"],
                  "border": f"1px solid {COLORS['border']}",
                  "padding": 20}),
    ], style={"padding": "0 28px 28px"}),

], style={"background": COLORS["bg"], "minHeight": "100vh", "fontFamily": "system-ui"})


@callback(
    Output("cmp-position-kpis",  "children"),
    Output("cmp-ranking-chart",  "figure"),
    Output("cmp-scatter-chart",  "figure"),
    Output("cmp-radar-chart",    "figure"),
    Input("cmp-year",        "value"),
    Input("cmp-peer-group",  "value"),
    Input("cmp-chapter",     "value"),
)
def update_comparison(year: int, peer_group: str, chapter: str):
    client = get_client()
    chapter = chapter or "6"   # inversiones por defecto

    base_cut = (
        f"year.fiscal_year:{year}"
        f"|data_type.data_type:liquidation"
        f"|chapter.chapter:{chapter}"
        f"|chapter.direction:expense"
    )

    # ── Ranking €/hab ─────────────────────────────────────────────────────────
    ranking_cells = client.aggregate(
        cube="municipal-spain",
        drilldown="municipality.name|municipality.ine_code|municipality.population",
        cut=base_cut,
        order="executed_per_capita:desc",
        pagesize=500,
        aggregates="executed_per_capita|execution_rate|modification_rate",
    )

    if not ranking_cells:
        empty = empty_state(f"Sin datos para el año {year} y el grupo seleccionado")
        return [], _empty_fig(), _empty_fig(), _empty_fig()

    df = pd.DataFrame(ranking_cells)
    df["epc"]     = pd.to_numeric(df.get("executed_per_capita.avg", 0), errors="coerce").fillna(0)
    df["exec_r"]  = pd.to_numeric(df.get("execution_rate.avg", 0),      errors="coerce").fillna(0)
    df["mod_r"]   = pd.to_numeric(df.get("modification_rate.avg", 0),   errors="coerce").fillna(0)
    df["is_jerez"]= df["municipality.ine_code"] == JEREZ_INE
    df["name"]    = df["municipality.name"].fillna("Desconocido")
    df = df.sort_values("epc", ascending=True).tail(30)

    jerez_row = df[df["is_jerez"]]
    all_names = df[~df["is_jerez"]]["name"].tolist()
    all_epc   = df[~df["is_jerez"]]["epc"].tolist()

    rank_fig = go.Figure()
    rank_fig.add_trace(go.Bar(
        y=all_names, x=all_epc,
        orientation="h",
        marker_color=COLORS["peers"],
        name="Municipios pares",
        showlegend=True,
    ))
    if not jerez_row.empty:
        rank_fig.add_trace(go.Bar(
            y=[JEREZ_NAME], x=[jerez_row["epc"].values[0]],
            orientation="h",
            marker_color=COLORS["jerez"],
            marker_line={"color": "#7C2D12", "width": 2},
            name="Jerez de la Frontera",
            showlegend=True,
        ))
    rank_fig.update_layout(**_chart_layout(height=max(300, len(df) * 22)),
                           xaxis_title="€/habitante ejecutados",
                           barmode="overlay",
                           legend={"orientation":"h","y":-0.15,"font":{"size":10}})

    # ── Scatter ejecución vs modificación ────────────────────────────────────
    scatter_cells = client.aggregate(
        cube="municipal-spain",
        drilldown="municipality.name|municipality.ine_code",
        cut=f"year.fiscal_year:{year}|data_type.data_type:liquidation",
        aggregates="expense_execution_rate|modification_rate|expense_executed_per_capita",
        pagesize=500,
    )

    sc_fig = go.Figure()
    if scatter_cells:
        sc_df = pd.DataFrame(scatter_cells)
        sc_df["exec_r"] = pd.to_numeric(sc_df.get("expense_execution_rate.avg"), errors="coerce")
        sc_df["mod_r"]  = pd.to_numeric(sc_df.get("modification_rate.avg"),      errors="coerce")
        sc_df["epc"]    = pd.to_numeric(sc_df.get("expense_executed_per_capita.avg"), errors="coerce")
        sc_df["is_j"]   = sc_df["municipality.ine_code"] == JEREZ_INE
        sc_df           = sc_df.dropna(subset=["exec_r", "mod_r"])

        peers_df = sc_df[~sc_df["is_j"]]
        jerez_sc = sc_df[sc_df["is_j"]]

        sc_fig.add_trace(go.Scatter(
            x=peers_df["mod_r"] * 100,
            y=peers_df["exec_r"] * 100,
            mode="markers",
            marker={"color": COLORS["peers"], "size": 7, "opacity": 0.6},
            text=peers_df["municipality.name"],
            hovertemplate="%{text}<br>Mod: %{x:.1f}%<br>Exec: %{y:.1f}%",
            name="Municipios pares",
        ))
        if not jerez_sc.empty:
            sc_fig.add_trace(go.Scatter(
                x=jerez_sc["mod_r"] * 100,
                y=jerez_sc["exec_r"] * 100,
                mode="markers+text",
                marker={"color": COLORS["jerez"], "size": 14,
                        "symbol": "star", "line": {"color": "#7C2D12", "width": 2}},
                text=["Jerez"],
                textposition="top center",
                name="Jerez",
            ))
        # Cuadrantes de referencia
        sc_fig.add_hline(y=85, line_dash="dash", line_color=COLORS["border"], line_width=1)
        sc_fig.add_vline(x=10, line_dash="dash", line_color=COLORS["border"], line_width=1)

    sc_fig.update_layout(
        **_chart_layout(height=320),
        xaxis_title="Tasa modificación (%)",
        yaxis_title="Tasa ejecución (%)",
    )

    # ── Radar funcional ───────────────────────────────────────────────────────
    func_cells = client.aggregate(
        cube="municipal-spain-func",
        drilldown="municipality.ine_code|area.area_code|area.area_name",
        cut=f"year.fiscal_year:{year}|data_type.data_type:liquidation",
        aggregates="executed_per_capita",
        pagesize=1000,
    )

    radar_fig = go.Figure()
    if func_cells:
        fc_df = pd.DataFrame(func_cells)
        fc_df["epc"] = pd.to_numeric(fc_df.get("executed_per_capita.avg"), errors="coerce")
        fc_df["area"] = fc_df["area.area_code"].astype(str)

        jerez_fc = fc_df[fc_df["municipality.ine_code"] == JEREZ_INE]
        peers_fc = fc_df[fc_df["municipality.ine_code"] != JEREZ_INE]

        areas     = [k for k in AREA_NAMES.keys() if k in fc_df["area"].values]
        areas_lbl = [AREA_NAMES.get(a, a) for a in areas]

        if areas and not jerez_fc.empty:
            def _area_vals(sub):
                vals = []
                for a in areas:
                    row = sub[sub["area"] == a]
                    vals.append(float(row["epc"].mean()) if not row.empty else 0)
                return vals

            jerez_vals = _area_vals(jerez_fc)
            peers_vals = _area_vals(peers_fc)

            radar_fig.add_trace(go.Scatterpolar(
                r=jerez_vals + [jerez_vals[0]],
                theta=areas_lbl + [areas_lbl[0]],
                fill="toself",
                name="Jerez",
                line_color=COLORS["jerez"],
                fillcolor=COLORS["jerez"] + "33",
            ))
            radar_fig.add_trace(go.Scatterpolar(
                r=peers_vals + [peers_vals[0]],
                theta=areas_lbl + [areas_lbl[0]],
                fill="toself",
                name="Media pares",
                line_color=COLORS["peers"],
                fillcolor=COLORS["peers"] + "22",
                line_dash="dash",
            ))

    radar_fig.update_layout(
        polar={"radialaxis": {"visible": True, "gridcolor": COLORS["border"]}},
        showlegend=True,
        **_chart_layout(height=340),
    )

    # ── KPIs de posición ──────────────────────────────────────────────────────
    position_kpis = []
    if not df.empty:
        df_sorted = df.sort_values("epc", ascending=False).reset_index(drop=True)
        jerez_rank = df_sorted[df_sorted["is_jerez"]].index
        jerez_rank_n = int(jerez_rank[0]) + 1 if len(jerez_rank) > 0 else None
        total = len(df_sorted)
        jerez_epc = float(jerez_row["epc"].values[0]) if not jerez_row.empty else None
        peers_avg = float(df[~df["is_jerez"]]["epc"].mean()) if not df[~df["is_jerez"]].empty else None
        diff = (jerez_epc - peers_avg) if jerez_epc and peers_avg else None

        position_kpis = [
            kpi_card("Posición en ranking",
                     f"{jerez_rank_n}º / {total}" if jerez_rank_n else "—",
                     "Por €/hab ejecutado", COLORS["jerez"]),
            kpi_card("Jerez €/hab",
                     f"{jerez_epc:,.0f} €" if jerez_epc else "—",
                     f"Cap. {chapter} · {year}", COLORS["jerez"]),
            kpi_card("Media del grupo",
                     f"{peers_avg:,.0f} €" if peers_avg else "—",
                     "€/hab ejecutado", COLORS["peers"]),
            kpi_card("Diferencia vs media",
                     f"{diff:+,.0f} €" if diff is not None else "—",
                     "Jerez sobre media pares",
                     COLORS["good"] if diff and diff >= 0 else COLORS["bad"]),
        ]

    return position_kpis, rank_fig, sc_fig, radar_fig


def _empty_fig() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="Sin datos", showarrow=False,
                       font={"color": COLORS["text_muted"], "size": 14})
    fig.update_layout(**_chart_layout())
    return fig


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

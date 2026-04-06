"""
Vista 3 — Explorador libre.

Permite seleccionar hasta 5 municipios y comparar:
  - Evolución temporal de una medida (líneas)
  - Desglose por capítulo para un año (barras agrupadas)
  - Tabla exportable a CSV
  - Enlace permanente con parámetros de la consulta (query string)
"""
from __future__ import annotations

import dash
from dash import dcc, html, Input, Output, State, callback, ctx
import plotly.graph_objects as go
import pandas as pd
import io

from dashboard.config import (
    COLORS, CHAPTER_NAMES, AVAILABLE_YEARS,
    JEREZ_INE, JEREZ_NAME, get_client,
)
from dashboard.components import (
    filter_bar, section_title, page_header, year_dropdown,
    chapter_dropdown, empty_state,
)

dash.register_page(__name__, path="/explorador", name="Explorador libre", order=2)


MEASURE_OPTIONS = [
    {"label": "€/habitante ejecutado",      "value": "executed_per_capita"},
    {"label": "Tasa de ejecución (%)",       "value": "execution_rate"},
    {"label": "Tasa de modificación (%)",    "value": "modification_rate"},
    {"label": "Importe ejecutado (€)",       "value": "executed_amount"},
]


layout = html.Div([

    page_header(
        "Explorador libre",
        "Compara hasta 5 municipios · Elige medida y clasificación · Exporta a CSV"
    ),

    filter_bar(
        html.Div([
            html.Label("Medida", style={
                "fontSize": 11, "fontWeight": 700, "color": COLORS["text_muted"],
                "textTransform": "uppercase", "letterSpacing": "0.06em",
                "marginBottom": 4, "display": "block",
            }),
            dcc.Dropdown(
                id="exp-measure",
                options=MEASURE_OPTIONS,
                value="executed_per_capita",
                clearable=False,
                style={"fontSize": 13, "width": 240},
            ),
        ]),
        html.Div(chapter_dropdown("exp-chapter", multi=True), style={"width": 300}),
        html.Div(year_dropdown("exp-year-start", years=AVAILABLE_YEARS,
                               value=2015, label="Desde"), style={"width": 110}),
        html.Div(year_dropdown("exp-year-end", years=AVAILABLE_YEARS,
                               value=2023, label="Hasta"), style={"width": 110}),
        html.Div([
            html.Label("Tipo de dato", style={
                "fontSize": 11, "fontWeight": 700, "color": COLORS["text_muted"],
                "textTransform": "uppercase", "letterSpacing": "0.06em",
                "marginBottom": 4, "display": "block",
            }),
            dcc.RadioItems(
                id="exp-data-type",
                options=[
                    {"label": "Liquidación", "value": "liquidation"},
                    {"label": "Presupuesto", "value": "budget"},
                ],
                value="liquidation",
                inline=True,
                labelStyle={"fontSize": 12, "marginRight": 12},
            ),
        ]),
    ),

    # Selector de municipios
    html.Div([
        html.Label("Municipios a comparar (hasta 5)", style={
            "fontSize": 11, "fontWeight": 700, "color": COLORS["text_muted"],
            "textTransform": "uppercase", "letterSpacing": "0.06em",
            "marginBottom": 6, "display": "block",
        }),
        dcc.Dropdown(
            id="exp-municipalities",
            options=[],                       # se puebla con callback
            value=[JEREZ_INE],
            multi=True,
            max_selectable=5,
            placeholder="Escribe el nombre o código INE del municipio...",
            style={"fontSize": 13},
        ),
        html.Div(id="exp-mun-search-trigger", style={"display": "none"}),
    ], style={"padding": "12px 28px"}),

    # Gráficos
    html.Div([
        html.Div([
            section_title("Evolución temporal"),
            dcc.Graph(id="exp-trend-chart", config={"displayModeBar": True}),
        ], style={"background": COLORS["surface"],
                  "border": f"1px solid {COLORS['border']}",
                  "padding": 20, "flex": 1}),
        html.Div([
            section_title("Desglose por capítulo (último año seleccionado)"),
            dcc.Graph(id="exp-chapter-chart", config={"displayModeBar": True}),
        ], style={"background": COLORS["surface"],
                  "border": f"1px solid {COLORS['border']}",
                  "padding": 20, "flex": 1, "marginLeft": 12}),
    ], style={"display": "flex", "padding": "0 28px 12px"}),

    # Tabla + export
    html.Div([
        html.Div([
            section_title("Tabla de datos"),
            html.Div(id="exp-table"),
            html.Div([
                html.Button("⬇ Descargar CSV", id="exp-download-btn",
                            style={
                                "background": COLORS["jerez"],
                                "color": "#fff", "border": "none",
                                "padding": "8px 16px", "cursor": "pointer",
                                "fontSize": 12, "fontWeight": 700,
                                "marginTop": 12,
                            }),
                dcc.Download(id="exp-download"),
            ]),
        ], style={"background": COLORS["surface"],
                  "border": f"1px solid {COLORS['border']}",
                  "padding": 20}),
    ], style={"padding": "0 28px 28px"}),

    # Store para datos de la tabla (para el export)
    dcc.Store(id="exp-data-store"),

], style={"background": COLORS["bg"], "minHeight": "100vh", "fontFamily": "system-ui"})


# ── Callback: poblar dropdown de municipios ───────────────────────────────────

@callback(
    Output("exp-municipalities", "options"),
    Input("exp-municipalities", "search_value"),
    prevent_initial_call=False,
)
def populate_municipalities(search: str):
    """Carga los primeros 200 municipios del cubo (o filtra por nombre)."""
    client = get_client()
    cut = None
    if search and len(search) >= 2:
        # No hay LIKE en babbage — obtenemos todos y filtramos en Python
        pass

    members = client.members(
        cube="municipal-spain",
        dimension="municipality",
        pagesize=200,
    )
    options = [
        {
            "label": f"{r.get('name', '?')} ({r.get('ine_code', '?')})",
            "value": r.get("ine_code", ""),
        }
        for r in members
        if not search or search.lower() in str(r.get("name", "")).lower()
    ]
    # Asegurar que Jerez siempre aparece al inicio
    jerez_opt = {"label": f"{JEREZ_NAME} ({JEREZ_INE})", "value": JEREZ_INE}
    if jerez_opt not in options:
        options = [jerez_opt] + options
    return options


# ── Callback principal ────────────────────────────────────────────────────────

@callback(
    Output("exp-trend-chart",   "figure"),
    Output("exp-chapter-chart", "figure"),
    Output("exp-table",         "children"),
    Output("exp-data-store",    "data"),
    Input("exp-municipalities", "value"),
    Input("exp-measure",        "value"),
    Input("exp-chapter",        "value"),
    Input("exp-year-start",     "value"),
    Input("exp-year-end",       "value"),
    Input("exp-data-type",      "value"),
)
def update_explorer(mun_codes, measure, chapters, year_start, year_end, data_type):
    if not mun_codes:
        mun_codes = [JEREZ_INE]

    client     = get_client()
    chapters   = chapters or list(CHAPTER_NAMES.keys())
    chapters   = chapters[:7]   # máximo 7
    year_start = year_start or 2015
    year_end   = year_end   or 2023

    # Nombre completo de la medida en babbage
    measure_key = {
        "executed_per_capita": "executed_per_capita.avg",
        "execution_rate":      "execution_rate.avg",
        "modification_rate":   "modification_rate.avg",
        "executed_amount":     "executed_amount.sum",
    }.get(measure, "executed_per_capita.avg")

    measure_label = next(
        (o["label"] for o in MEASURE_OPTIONS if o["value"] == measure),
        measure
    )

    palette = [
        COLORS["jerez"], COLORS["peers"],
        "#059669", "#7C3AED", "#DB2777",
    ]

    # ── Evolución temporal ────────────────────────────────────────────────────
    trend_fig = go.Figure()
    all_rows  = []

    for i, ine in enumerate(mun_codes[:5]):
        cut_parts = [
            f"data_type.data_type:{data_type}",
            f"municipality.ine_code:{ine}",
            f"year.fiscal_year:{year_start};{year_end}",
        ]
        if len(chapters) == 1:
            cut_parts.append(f"chapter.chapter:{chapters[0]}")
            cut_parts.append("chapter.direction:expense")

        cells = client.aggregate(
            cube="municipal-spain",
            drilldown="year.fiscal_year|municipality.name",
            cut="|".join(cut_parts),
            order="year.fiscal_year:asc",
            aggregates=measure,
            pagesize=200,
        )
        if not cells:
            continue

        name  = cells[0].get("municipality.name", ine) if cells else ine
        years = [r["year.fiscal_year"] for r in cells]
        vals  = [_f(r, measure_key) for r in cells]
        color = palette[i % len(palette)]

        trend_fig.add_trace(go.Scatter(
            x=years, y=vals, name=name,
            line={"color": color, "width": 2.5 if ine == JEREZ_INE else 1.5},
            mode="lines+markers",
            marker={"size": 6, "color": color},
        ))

        for r in cells:
            all_rows.append({
                "municipio": name,
                "ine_code":  ine,
                "año":       r["year.fiscal_year"],
                measure_label: _f(r, measure_key),
            })

    trend_fig.update_layout(
        **_chart_layout(height=300),
        yaxis_title=measure_label,
        xaxis={"dtick": 1},
        legend={"orientation": "h", "y": -0.25, "font": {"size": 10}},
    )

    # ── Desglose por capítulo (último año) ────────────────────────────────────
    ch_fig = go.Figure()
    for i, ine in enumerate(mun_codes[:5]):
        cut_parts = [
            f"data_type.data_type:{data_type}",
            f"municipality.ine_code:{ine}",
            f"year.fiscal_year:{year_end}",
            "chapter.direction:expense",
        ]
        cells = client.aggregate(
            cube="municipal-spain",
            drilldown="chapter.chapter|municipality.name",
            cut="|".join(cut_parts),
            order="chapter.chapter:asc",
            aggregates=measure,
            pagesize=20,
        )
        if not cells:
            continue
        name    = cells[0].get("municipality.name", ine)
        ch_vals = {str(r["chapter.chapter"]): _f(r, measure_key) for r in cells}
        color   = palette[i % len(palette)]

        ch_fig.add_trace(go.Bar(
            name=name,
            x=[CHAPTER_NAMES.get(c, f"Cap.{c}") for c in CHAPTER_NAMES if c in ch_vals],
            y=[ch_vals.get(c, 0) for c in CHAPTER_NAMES if c in ch_vals],
            marker_color=color,
            opacity=0.85,
        ))

    ch_fig.update_layout(
        **_chart_layout(height=300),
        barmode="group",
        yaxis_title=measure_label,
        legend={"orientation": "h", "y": -0.3, "font": {"size": 10}},
    )

    # ── Tabla ─────────────────────────────────────────────────────────────────
    table_html = _build_table(all_rows, measure_label) if all_rows else empty_state()

    return trend_fig, ch_fig, table_html, all_rows


@callback(
    Output("exp-download", "data"),
    Input("exp-download-btn", "n_clicks"),
    State("exp-data-store", "data"),
    prevent_initial_call=True,
)
def download_csv(n_clicks, data):
    if not data:
        return dash.no_update
    df = pd.DataFrame(data)
    return dcc.send_data_frame(df.to_csv, "jerezbudget_comparativa.csv", index=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(row: dict, key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _build_table(rows: list[dict], measure_label: str) -> html.Table:
    if not rows:
        return empty_state()
    df = pd.DataFrame(rows).round(2)
    return html.Table([
        html.Thead(html.Tr([
            html.Th(col, style={"padding": "6px 10px", "textAlign": "left",
                                "fontSize": 11, "color": COLORS["text_muted"],
                                "background": COLORS["bg"],
                                "textTransform": "uppercase", "letterSpacing": "0.05em"})
            for col in df.columns
        ])),
        html.Tbody([
            html.Tr([
                html.Td(str(v), style={
                    "padding": "5px 10px", "fontSize": 12,
                    "color": COLORS["jerez"] if col == "municipio"
                             and "Jerez" in str(v) else COLORS["text"],
                    "borderBottom": f"1px solid {COLORS['border']}",
                })
                for col, v in zip(df.columns, row)
            ])
            for row in df.itertuples(index=False)
        ]),
    ], style={
        "width": "100%", "borderCollapse": "collapse",
        "fontSize": 12, "fontFamily": "monospace",
    })


def _chart_layout(height: int = 320) -> dict:
    return {
        "height": height,
        "margin": {"t": 10, "b": 50, "l": 10, "r": 20},
        "paper_bgcolor": COLORS["surface"],
        "plot_bgcolor":  COLORS["bg"],
        "font": {"family": "system-ui", "size": 11, "color": COLORS["text"]},
        "xaxis": {"gridcolor": COLORS["border"]},
        "yaxis": {"gridcolor": COLORS["border"]},
    }

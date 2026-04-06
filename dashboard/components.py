"""
Componentes Dash reutilizables entre las tres vistas del dashboard.
"""
from __future__ import annotations

from dash import dcc, html

from dashboard.config import COLORS, AVAILABLE_YEARS, JEREZ_YEARS, PEER_GROUPS


def page_header(title: str, subtitle: str = "") -> html.Div:
    return html.Div([
        html.H1(title, style={
            "margin": 0, "fontSize": 22, "fontWeight": 800,
            "color": COLORS["text"], "letterSpacing": "-0.02em",
        }),
        html.P(subtitle, style={
            "margin": "4px 0 0", "fontSize": 13,
            "color": COLORS["text_muted"],
        }) if subtitle else None,
    ], style={
        "padding": "20px 28px 16px",
        "borderBottom": f"1px solid {COLORS['border']}",
        "background": COLORS["surface"],
    })


def kpi_card(
    title: str,
    value: str,
    subtitle: str = "",
    color: str = COLORS["jerez"],
    trend: str = "",
) -> html.Div:
    """Tarjeta de KPI con valor grande y subtítulo."""
    return html.Div([
        html.Div(title, style={
            "fontSize": 11, "fontWeight": 700,
            "color": COLORS["text_muted"],
            "textTransform": "uppercase",
            "letterSpacing": "0.06em",
            "marginBottom": 6,
        }),
        html.Div(value, style={
            "fontSize": 28, "fontWeight": 900,
            "color": color, "fontFamily": "monospace",
            "letterSpacing": "-0.02em",
            "lineHeight": 1,
        }),
        html.Div(
            [subtitle, html.Span(f" {trend}", style={"color": color}) if trend else ""],
            style={"fontSize": 11, "color": COLORS["text_muted"], "marginTop": 4}
        ) if subtitle else None,
    ], style={
        "background": COLORS["surface"],
        "border": f"1px solid {COLORS['border']}",
        "borderTop": f"3px solid {color}",
        "padding": "14px 16px",
        "borderRadius": 0,
    })


def score_gauge(score: float | None, label: str, size: int = 160) -> html.Div:
    """Gauge circular para mostrar un score 0-100."""
    import plotly.graph_objects as go
    from dash import dcc

    if score is None:
        display = "N/D"
        color = COLORS["text_muted"]
        val = 0
    else:
        display = f"{score:.1f}"
        val = score
        if score >= 75:
            color = COLORS["good"]
        elif score >= 50:
            color = COLORS["warn"]
        else:
            color = COLORS["bad"]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        number={"font": {"size": 28, "color": color}, "suffix": ""},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": COLORS["border"]},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": COLORS["bg"],
            "borderwidth": 0,
            "steps": [
                {"range": [0, 50],  "color": "#FEE2E2"},
                {"range": [50, 75], "color": "#FEF3C7"},
                {"range": [75, 100],"color": "#D1FAE5"},
            ],
        },
        title={"text": label, "font": {"size": 12, "color": COLORS["text_muted"]}},
    ))
    fig.update_layout(
        height=size, margin={"t": 30, "b": 10, "l": 20, "r": 20},
        paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        font={"family": "system-ui"},
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def year_dropdown(
    id: str,
    years: list[int] = AVAILABLE_YEARS,
    value: int | None = None,
    label: str = "Año",
) -> html.Div:
    return html.Div([
        html.Label(label, style={
            "fontSize": 11, "fontWeight": 700, "color": COLORS["text_muted"],
            "textTransform": "uppercase", "letterSpacing": "0.06em",
            "marginBottom": 4, "display": "block",
        }),
        dcc.Dropdown(
            id=id,
            options=[{"label": str(y), "value": y} for y in sorted(years, reverse=True)],
            value=value or max(years),
            clearable=False,
            style={"fontSize": 13},
        ),
    ])


def peer_group_dropdown(id: str) -> html.Div:
    return html.Div([
        html.Label("Grupo de comparación", style={
            "fontSize": 11, "fontWeight": 700, "color": COLORS["text_muted"],
            "textTransform": "uppercase", "letterSpacing": "0.06em",
            "marginBottom": 4, "display": "block",
        }),
        dcc.Dropdown(
            id=id,
            options=[{"label": v, "value": k} for k, v in PEER_GROUPS.items()],
            value="andalucia-100k-250k",
            clearable=False,
            style={"fontSize": 13},
        ),
    ])


def chapter_dropdown(id: str, multi: bool = False) -> html.Div:
    from dashboard.config import CHAPTER_NAMES
    return html.Div([
        html.Label("Capítulo económico", style={
            "fontSize": 11, "fontWeight": 700, "color": COLORS["text_muted"],
            "textTransform": "uppercase", "letterSpacing": "0.06em",
            "marginBottom": 4, "display": "block",
        }),
        dcc.Dropdown(
            id=id,
            options=[{"label": v, "value": k} for k, v in CHAPTER_NAMES.items()],
            value=None if multi else "6",
            multi=multi,
            placeholder="Todos los capítulos" if multi else None,
            style={"fontSize": 13},
        ),
    ])


def filter_bar(*children) -> html.Div:
    """Barra de filtros horizontal con los selectores dados."""
    return html.Div(
        children,
        style={
            "display": "flex", "gap": 16, "padding": "16px 28px",
            "background": COLORS["surface"],
            "borderBottom": f"1px solid {COLORS['border']}",
            "flexWrap": "wrap",
            "alignItems": "flex-end",
        }
    )


def section_title(text: str) -> html.H3:
    return html.H3(text, style={
        "fontSize": 13, "fontWeight": 700, "color": COLORS["text"],
        "margin": "0 0 12px",
        "paddingBottom": 8,
        "borderBottom": f"1px solid {COLORS['border']}",
        "textTransform": "uppercase",
        "letterSpacing": "0.08em",
    })


def alert_box(message: str, type_: str = "info") -> html.Div:
    color_map = {
        "info":    ("#DBEAFE", "#1E40AF"),
        "warning": ("#FEF3C7", "#92400E"),
        "error":   ("#FEE2E2", "#991B1B"),
        "success": ("#D1FAE5", "#065F46"),
    }
    bg, fg = color_map.get(type_, color_map["info"])
    return html.Div(message, style={
        "background": bg, "color": fg,
        "padding": "10px 14px", "fontSize": 13,
        "border": f"1px solid {fg}44",
        "marginBottom": 16,
    })


def empty_state(message: str = "Sin datos disponibles") -> html.Div:
    return html.Div([
        html.Div("📊", style={"fontSize": 36, "marginBottom": 8}),
        html.P(message, style={"color": COLORS["text_muted"], "fontSize": 13}),
    ], style={
        "textAlign": "center", "padding": "48px 20px",
        "background": COLORS["surface"],
    })

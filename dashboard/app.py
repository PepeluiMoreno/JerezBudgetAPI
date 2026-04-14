"""
Aplicación principal Dash — JerezBudget Dashboard.

Estructura multi-página con Dash Pages:
  /rigor        → Vista 1: Score de rigor de Jerez
  /comparativa  → Vista 2: Comparativa entre ciudades
  /explorador   → Vista 3: Explorador libre

Consumo de la API babbage en http://api:8015/api/3
Configurable via variable de entorno BABBAGE_BASE_URL.
"""
from __future__ import annotations

import dash
from dash import dcc, html, Input, Output, State, callback, ALL
from dash.exceptions import PreventUpdate

from dashboard.config import COLORS, DASH_HOST, DASH_PORT, DASH_DEBUG, DASH_PREFIX, API_PUBLIC_URL
from dashboard.components import INFO_DEFINITIONS

# ── App ───────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    url_base_pathname=DASH_PREFIX + "/" if DASH_PREFIX else "/",
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Dashboard de rigor presupuestario municipal"},
    ],
    title="JerezBudget — Rigor Presupuestario",
)
server = app.server   # WSGI server para Gunicorn

# ── Helpers ───────────────────────────────────────────────────────────────────

def _nav_link(label: str, href: str, icon: str) -> html.A:
    slug = label.lower()
    return html.A(
        [icon, " ", label],
        id=f"nav-{slug}",
        href=href,
        style={
            "display": "flex", "alignItems": "center", "gap": 5,
            "padding": "6px 12px", "borderRadius": 4,
            "color": "#9CA3AF",
            "textDecoration": "none", "fontSize": 13,
        }
    )


def _ext_link_style() -> dict:
    return {
        "color": "#6B7280", "fontSize": 11,
        "textDecoration": "none", "padding": "4px 8px",
        "border": "1px solid #374151", "borderRadius": 3,
    }


# ── Layout principal ──────────────────────────────────────────────────────────

app.layout = html.Div([

    # ── Navbar ────────────────────────────────────────────────────────────────
    html.Nav([
        # Logo / título
        html.Div([
            html.A([
                html.Span("Jerez", style={
                    "color": COLORS["jerez"], "fontWeight": 900,
                    "fontSize": 15, "letterSpacing": "-0.02em",
                }),
                html.Span("Budget", style={
                    "color": "#fff", "fontWeight": 700,
                    "fontSize": 15, "letterSpacing": "-0.02em",
                }),
            ], href="/rigor", style={"textDecoration": "none"}),
            html.Span("· Rigor Presupuestario Municipal", style={
                "color": "#6B7280", "fontSize": 12, "marginLeft": 8,
            }),
        ], style={"display": "flex", "alignItems": "center"}),

        # Navegación
        html.Div([
            _nav_link("Rigor",        "/rigor",       "📊"),
            _nav_link("Comparativa",  "/comparativa", "🏙️"),
            _nav_link("Explorador",   "/explorador",  "🔍"),
        ], style={"display": "flex", "gap": 4}),

        # Links externos
        html.Div([
            html.A("GraphiQL", href=f"{API_PUBLIC_URL}/graphql", target="_blank", style=_ext_link_style()),
            html.A("API OLAP",  href=f"{API_PUBLIC_URL}/api/3/cubes/", target="_blank", style=_ext_link_style()),
            html.A("GitHub",    href="https://github.com/PepeluiMoreno/JerezBudgetAPI",
                   target="_blank", style=_ext_link_style()),
        ], style={"display": "flex", "gap": 8, "marginLeft": "auto",
                  "alignItems": "center"}),

    ], style={
        "display": "flex", "alignItems": "center",
        "padding": "0 28px",
        "height": 52,
        "background": "#111827",
        "borderBottom": f"2px solid {COLORS['jerez']}",
        "position": "sticky", "top": 0, "zIndex": 100,
    }),

    # ── Contenido de la página activa ─────────────────────────────────────────
    dash.page_container,

    # ── Modal global de información de indicadores ────────────────────────────
    html.Div(
        id="info-modal-overlay",
        children=[
            # Backdrop — clic cierra el modal
            html.Div(id="info-modal-backdrop", style={
                "position": "fixed", "inset": 0,
                "background": "rgba(0,0,0,0.45)",
                "zIndex": 999,
            }),
            # Tarjeta del modal
            html.Div([
                html.Div([
                    html.Div(id="info-modal-title", style={
                        "fontSize": 16, "fontWeight": 700,
                        "color": COLORS["text"], "flex": 1,
                    }),
                    html.Button("✕", id="info-modal-close", n_clicks=0, style={
                        "background": "none", "border": "none",
                        "fontSize": 18, "cursor": "pointer",
                        "color": COLORS["text_muted"], "padding": "0 4px",
                        "lineHeight": 1,
                    }),
                ], style={"display": "flex", "alignItems": "flex-start",
                          "marginBottom": 14}),
                html.Div(id="info-modal-body", style={
                    "fontSize": 13, "color": COLORS["text_muted"],
                    "lineHeight": 1.7, "whiteSpace": "pre-line",
                }),
            ], style={
                "position": "fixed",
                "top": "50%", "left": "50%",
                "transform": "translate(-50%,-50%)",
                "background": COLORS["surface"],
                "border": f"1px solid {COLORS['border']}",
                "borderTop": f"3px solid {COLORS['good']}",
                "borderRadius": 4,
                "padding": "24px 28px",
                "width": 420,
                "maxWidth": "90vw",
                "zIndex": 1000,
                "boxShadow": "0 8px 32px rgba(0,0,0,0.25)",
            }),
        ],
        style={"display": "none"},   # oculto por defecto
    ),

    # ── Footer ────────────────────────────────────────────────────────────────
    html.Footer([
        html.Span("JerezBudget API · ", style={"color": "#6B7280", "fontSize": 11}),
        html.A("github.com/PepeluiMoreno/JerezBudgetAPI",
               href="https://github.com/PepeluiMoreno/JerezBudgetAPI",
               target="_blank",
               style={"color": COLORS["jerez"], "fontSize": 11}),
        html.Span(" · Datos: CONPREL (Ministerio de Hacienda) + transparencia.jerez.es",
                  style={"color": "#6B7280", "fontSize": 11}),
    ], style={
        "padding": "12px 28px",
        "background": "#111827",
        "borderTop": f"1px solid #1F2937",
        "textAlign": "center",
        "marginTop": "auto",
    }),

], style={
    "minHeight": "100vh",
    "display": "flex",
    "flexDirection": "column",
    "fontFamily": "-apple-system, 'Helvetica Neue', sans-serif",
    "background": COLORS["bg"],
})


# ── Redirección raíz → /rigor ─────────────────────────────────────────────────

@callback(
    Output("_pages_location", "pathname"),
    Input("_pages_location",  "pathname"),
)
def redirect_root(pathname: str):
    if pathname in ("/", ""):
        return "/rigor"
    raise PreventUpdate


# ── Highlight de la pestaña activa ────────────────────────────────────────────

@callback(
    Output("nav-rigor",       "style"),
    Output("nav-comparativa", "style"),
    Output("nav-explorador",  "style"),
    Input("_pages_location",  "pathname"),
)
def highlight_active_nav(pathname: str):
    active = {
        "display": "flex", "alignItems": "center", "gap": 5,
        "padding": "6px 12px", "borderRadius": 4,
        "color": COLORS["jerez"],
        "background": COLORS["jerez"] + "22",
        "textDecoration": "none", "fontSize": 13, "fontWeight": 700,
    }
    inactive = {
        "display": "flex", "alignItems": "center", "gap": 5,
        "padding": "6px 12px", "borderRadius": 4,
        "color": "#9CA3AF",
        "textDecoration": "none", "fontSize": 13, "fontWeight": 400,
    }
    paths = ["/rigor", "/comparativa", "/explorador"]
    styles = []
    for p in paths:
        styles.append(active if (pathname or "").startswith(p) else inactive)
    return styles


# ── Modal de información ──────────────────────────────────────────────────────

@callback(
    Output("info-modal-overlay", "style"),
    Output("info-modal-title",   "children"),
    Output("info-modal-body",    "children"),
    Input({"type": "info-btn", "index": ALL}, "n_clicks"),
    Input("info-modal-close",    "n_clicks"),
    Input("info-modal-backdrop", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_info_modal(btn_clicks, close_clicks, backdrop_clicks):
    from dash import ctx
    hidden = {"display": "none"}
    visible = {"display": "block"}

    trigger = ctx.triggered_id

    # Cerrar si se pulsó X o el backdrop
    if trigger in ("info-modal-close", "info-modal-backdrop"):
        return hidden, "", ""

    # Abrir si se pulsó algún botón de info
    if isinstance(trigger, dict) and trigger.get("type") == "info-btn":
        key = trigger["index"]
        defn = INFO_DEFINITIONS.get(key, {})
        if not defn:
            raise PreventUpdate
        # Verificar que el click fue real (n_clicks > 0)
        clicked_values = btn_clicks or []
        if not any(v and v > 0 for v in clicked_values):
            raise PreventUpdate
        return visible, defn["title"], defn["body"]

    raise PreventUpdate


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host=DASH_HOST,
        port=DASH_PORT,
        debug=DASH_DEBUG,
    )

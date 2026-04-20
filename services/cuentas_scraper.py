"""
Scraper del Portal del Ciudadano — rendiciondecuentas.es.

Extrae KPIs de sostenibilidad de la Cuenta General (modelos NOR) directamente
del portal público del Tribunal de Cuentas, ya que no existe API REST pública.

Flujo de sesión (necesita requests, no httpx, por conflicto de JSESSIONID dual):
  1. GET base page                         → portal JSESSIONID (path=/)
  2. GET consultarCuenta?…&option=vc       → 302 a CargarVisualizadorServlet
  3. GET CargarVisualizadorServlet         → Tomcat JSESSIONID (path=/VisualizadorPortalCiudadano) → 302
  4. GET VisualizadorPortal.jsp            → 200 HTML con 99 links a ServletDatos
  5. GET ServletDatos?id_form=…           → 200 HTML tabla con datos financieros

Fuentes de KPIs:
  - IndFinYPatri     → 12 indicadores financiero-patrimoniales oficiales + magnitudes absolutas
  - RemanenteTesoreria → RTGG y RT total (Ejercicio Actual + Anterior)
  - CuentaResultado  → ingresos/gastos gestión ordinaria, resultado del ejercicio (Actual + Anterior)
  - Balance          → activo total (Actual + Anterior)

Unidades:
  - Valores monetarios: EUR (Decimal de 2 decimales)
  - Ratios/porcentajes: adimensional (Decimal)
  - Días (PMP, PMC): Decimal
  - Habitantes: entero almacenado como Decimal

Uso:
    from services.cuentas_scraper import scrape_cg_kpis
    kpis = scrape_cg_kpis(nif="P1102000E", id_entidad=1779, ejercicio=2022)
    # Returns list[dict] ready for upsert into cuenta_general_kpis
"""
from __future__ import annotations

import html as html_module
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests
from bs4 import BeautifulSoup

import structlog
logger = structlog.get_logger(__name__)

_BASE = "https://www.rendiciondecuentas.es"
_VIZ  = _BASE + "/VisualizadorPortalCiudadano"

# ── IndFinYPatri column name → KPI name + unit ────────────────────────────────
# Each table in IndFinYPatri is a formula: input columns + calculated last column.
# IMPORTANT — tables 9 and 10 ("income/expense structure") have a mixed format:
#   col 0 = absolute total (EUR), cols 1-N = component RATIOS (fraction of total).
# All other tables have absolute EUR values in all columns except the last.
# Columns that are intermediate calculations ("Sumatorio de…") are excluded.
_IFP_COL_MAP: dict[str, tuple[str, str]] = {
    # ── Absolute magnitudes (EUR / HAB) ────────────────────────────────────────
    "Fondos líquidos":          ("fondos_liquidos",           "EUR"),
    "Pasivo corriente":         ("pasivo_corriente",          "EUR"),
    "Derechos pendientes de cobro": ("derechos_pendientes_cobro", "EUR"),
    "Activo corriente":         ("activo_corriente",          "EUR"),
    "Pasivo no corriente":      ("pasivo_no_corriente",       "EUR"),
    "Número de habitantes":     ("habitantes",                "HAB"),
    "Patrimonio neto":          ("patrimonio_neto",           "EUR"),
    "Flujos netos de gestión":  ("flujos_netos_gestion",      "EUR"),
    # ── Calculated ratios / indicators (last col of each table) ────────────────
    "Liquidez inmediata":       ("liquidez_inmediata",        "RAT"),
    "Liquidez a corto plazo":   ("liquidez_corto_plazo",      "RAT"),
    "Liquidez general":         ("liquidez_general",          "RAT"),
    "Endeudamiento por habitante": ("endeudamiento_habitante", "EUR"),
    "Endeudamiento":            ("endeudamiento",             "RAT"),
    "Relación de endeudamiento":("relacion_endeudamiento",    "RAT"),
    "Cash-flow":                ("cash_flow",                 "RAT"),
    "Periodo medio de pago a acreedores comerciales": ("pmp_acreedores", "DIA"),
    "Periodo medio de cobro":   ("periodo_medio_cobro",       "DIA"),
    # ── Income structure (tables 9): cols 1-4 are RATIOS (component/total) ─────
    # Column 0 "Ingresos de gestión ordinaria" = absolute EUR — skip (see CuentaResultado)
    "Ingresos tributarios y urbanísticos":     ("ratio_ingresos_tributarios",      "RAT"),
    "Transferencias y subvenciones recibidas": ("ratio_transferencias_recibidas",  "RAT"),
    "Ventas y prestación de servicios":        ("ratio_ingresos_ventas",           "RAT"),
    "Resto ingresos de gestión ordinaria":     ("ratio_resto_ingresos",            "RAT"),
    # ── Expense structure (table 10): cols 1-4 are RATIOS (component/total) ────
    # Column 0 "Gastos de gestión ordinaria" = absolute EUR — skip (see CuentaResultado)
    "Gastos de personal":                      ("ratio_gastos_personal",           "RAT"),
    "Transferencias y subvenciones concedidas":("ratio_transferencias_concedidas", "RAT"),
    "Aprovisionamientos":                      ("ratio_aprovisionamientos",        "RAT"),
    "Resto gastos de gestión ordinaria":       ("ratio_resto_gastos",              "RAT"),
    # ── Coverage ratio (table 11) ──────────────────────────────────────────────
    "Cobertura de los gastos corrientes":      ("cobertura_gastos_corrientes",     "RAT"),
}

# ── RemanenteTesoreria key rows ───────────────────────────────────────────────
_RT_ROWS: dict[str, str] = {
    "remanente de tesorería total":               "remanente_tesoreria_total",
    "remanente de tesorería para gastos general": "remanente_tesoreria_gastos_generales",
}

# ── CuentaResultado key rows ──────────────────────────────────────────────────
# Partial match of lowercased label → KPI name
_CR_ROWS: dict[str, str] = {
    "total ingresos de gestión ordinaria":  "ingresos_gestion_ordinaria_cr",
    "total gastos de gestión ordinaria":    "gastos_gestion_ordinaria_cr",
    "resultado (ahorro o desahorro) de la gestión ordinaria": "resultado_gestion_ordinaria",
    "resultado de las operaciones no financieras": "resultado_operaciones_no_financieras",
    "resultado (ahorro o desahorro) neto del ejercicio": "resultado_neto_ejercicio",
}

# ── Balance key rows ──────────────────────────────────────────────────────────
_BAL_ROWS: dict[str, str] = {
    "(a+b)total activo":              "activo_total",
    "(a+b+c)total patrimonio neto y pasivo": "total_pneto_y_pasivo",
}


def scrape_cg_kpis(
    nif: str,
    id_entidad: int,
    ejercicio: int,
    id_entidad_ppal: Optional[int] = None,
    id_tipo_entidad: str = "A",
    modelo: int = 3,
) -> list[dict]:
    """
    Scrapes Cuenta General KPIs for an entity and year from rendiciondecuentas.es.

    Returns a list of dicts suitable for upserting into cuenta_general_kpis.
    Each dict has keys: nif_entidad, ejercicio, kpi, valor, unidad, fuente_cuenta.

    Raises ValueError if the ejercicio is not available (403).
    Raises requests.HTTPError on network/server errors.
    """
    if id_entidad_ppal is None:
        id_entidad_ppal = id_entidad

    logger.info("cg_scrape_start", nif=nif, id_entidad=id_entidad, ejercicio=ejercicio)

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    })

    # ── Step 1: Load base page to establish portal JSESSIONID ─────────────────
    base_page_url = (
        f"{_BASE}/es/consultadeentidadesycuentas/buscarCuentas/consultarCuenta.html"
        f"?idEntidad={id_entidad}&ejercicio={ejercicio}"
    )
    session.get(base_page_url, timeout=30)

    # ── Step 2: Initiate account view → 302 to CargarVisualizadorServlet ──────
    vc_url = (
        f"{_BASE}/es/consultadeentidadesycuentas/buscarCuentas/consultarCuenta.html"
        f"?dd=true&idEntidadPpal={id_entidad_ppal}&idEntidad={id_entidad}"
        f"&idTipoEntidad={id_tipo_entidad}&idModelo={modelo}"
        f"&ejercicio={ejercicio}&nifEntidad={nif}&option=vc"
    )
    r_vc = session.get(vc_url, allow_redirects=False, timeout=30)
    if r_vc.status_code == 403:
        raise ValueError(
            f"Ejercicio {ejercicio} no disponible en rendiciondecuentas.es "
            f"para entidad {id_entidad} (HTTP 403)"
        )
    if r_vc.status_code != 302:
        raise ValueError(
            f"Respuesta inesperada de consultarCuenta: HTTP {r_vc.status_code}"
        )
    cargar_url = r_vc.headers["location"]

    # ── Step 3: CargarVisualizadorServlet → Tomcat JSESSIONID ─────────────────
    r_cargar = session.get(cargar_url, allow_redirects=False, timeout=30)
    session.headers.update({"Referer": cargar_url})

    # ── Step 4: VisualizadorPortal.jsp — JSP registers session state in Tomcat ─
    viz_url = _VIZ + "/VisualizadorPortal.jsp"
    r_viz = session.get(viz_url, allow_redirects=False, timeout=30)
    r_viz.raise_for_status()
    if r_viz.status_code != 200 or len(r_viz.content) < 5000:
        raise ValueError(
            f"VisualizadorPortal.jsp devolvió status={r_viz.status_code}, "
            f"size={len(r_viz.content)} — sesión inválida"
        )

    # ── Step 5: Build id_form → URL map ───────────────────────────────────────
    session.headers.update({"Referer": viz_url})
    raw_links = re.findall(r'ServletDatos\?[^"\'<>\s]+', r_viz.text)
    links_map: dict[str, str] = {}
    for raw in raw_links:
        clean = html_module.unescape(raw)
        m = re.search(r'id_form=([^&]+)', clean)
        if m:
            links_map[m.group(1)] = clean

    logger.info("cg_scrape_forms_found", count=len(links_map), ejercicio=ejercicio)

    kpis: list[dict] = []

    # ── Extract IndFinYPatri (official indicators, current year only) ──────────
    if "IndFinYPatri" in links_map:
        kpis.extend(_parse_ind_fin_y_patri(session, _VIZ + "/" + links_map["IndFinYPatri"], nif, ejercicio))
    else:
        logger.warning("cg_scrape_missing_form", form="IndFinYPatri", ejercicio=ejercicio)

    # ── Extract RemanenteTesoreria (2 years) ───────────────────────────────────
    if "RemanenteTesoreria" in links_map:
        kpis.extend(_parse_two_year_table(
            session, _VIZ + "/" + links_map["RemanenteTesoreria"],
            nif, ejercicio, _RT_ROWS,
        ))
    else:
        logger.warning("cg_scrape_missing_form", form="RemanenteTesoreria", ejercicio=ejercicio)

    # ── Extract CuentaResultado (2 years) ──────────────────────────────────────
    if "CuentaResultado" in links_map:
        kpis.extend(_parse_two_year_table(
            session, _VIZ + "/" + links_map["CuentaResultado"],
            nif, ejercicio, _CR_ROWS,
        ))
    else:
        logger.warning("cg_scrape_missing_form", form="CuentaResultado", ejercicio=ejercicio)

    # ── Extract Balance (2 years) ─────────────────────────────────────────────
    if "Balance" in links_map:
        kpis.extend(_parse_balance(
            session, _VIZ + "/" + links_map["Balance"],
            nif, ejercicio,
        ))
    else:
        logger.warning("cg_scrape_missing_form", form="Balance", ejercicio=ejercicio)

    logger.info("cg_scrape_done", kpis_extracted=len(kpis), ejercicio=ejercicio)
    return kpis


# ── Private parsers ───────────────────────────────────────────────────────────

def _parse_ind_fin_y_patri(
    session: requests.Session,
    url: str,
    nif: str,
    ejercicio: int,
) -> list[dict]:
    """
    Parses the IndFinYPatri state.

    Each table has column headers: [var1, var2, …, calculated_indicator].
    We extract every column whose header is in _IFP_COL_MAP.
    All values are for the current ejercicio only (no "ejercicio anterior" column).
    """
    r = session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    seen_kpis: set[str] = set()  # avoid duplicates when same variable appears in multiple tables
    records: list[dict] = []

    for table in soup.find_all("table"):
        header_cells = table.find("tr").find_all("th") if table.find("tr") else []
        col_names = [th.get_text(strip=True) for th in header_cells]

        # Find the data row (first tr with td cells)
        data_cells: list = []
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if tds:
                data_cells = tds
                break

        if not data_cells or len(data_cells) != len(col_names):
            continue

        for col_idx, col_name in enumerate(col_names):
            if col_name not in _IFP_COL_MAP:
                continue
            kpi_name, unit = _IFP_COL_MAP[col_name]
            if kpi_name in seen_kpis:
                continue
            valor = _parse_decimal(data_cells[col_idx].get_text(strip=True))
            if valor is None:
                continue
            seen_kpis.add(kpi_name)
            records.append({
                "nif_entidad":      nif,
                "ejercicio":        ejercicio,
                "kpi":              kpi_name,
                "valor":            valor,
                "unidad":           unit,
                "fuente_cuenta":    "rendiciondecuentas_cg",
                "odmgr_dataset_id": None,
            })

    return records


def _parse_two_year_table(
    session: requests.Session,
    url: str,
    nif: str,
    ejercicio: int,
    row_map: dict[str, str],
) -> list[dict]:
    """
    Generic parser for tables with 'Ejercicio Actual | Ejercicio Anterior' columns.

    row_map: partial lowercase match of row label → KPI name.
    Both years are persisted as separate records.
    """
    r = session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    # Find column index for Ejercicio Actual / Anterior
    # Typical structure: [label_col, (nota_col?), actual_col, anterior_col]
    header_row = soup.find("tr")
    col_headers: list[str] = []
    if header_row:
        col_headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

    # Determine which td indices hold the two year values
    actual_idx:   Optional[int] = None
    anterior_idx: Optional[int] = None
    for i, h in enumerate(col_headers):
        if "actual" in h.lower():
            actual_idx = i
        elif "anterior" in h.lower():
            anterior_idx = i

    # Fallback: assume label=0, (nota=1), actual=2, anterior=3
    if actual_idx is None:
        actual_idx   = 2 if len(col_headers) >= 4 else 1
    if anterior_idx is None:
        anterior_idx = 3 if len(col_headers) >= 4 else 2

    year_map = {actual_idx: ejercicio, anterior_idx: ejercicio - 1}

    records: list[dict] = []
    for row in soup.find_all("tr"):
        tds = row.find_all("td")
        if not tds:
            continue
        label = tds[0].get_text(strip=True).lower()

        kpi_name: Optional[str] = None
        for kw, name in row_map.items():
            if kw in label:
                kpi_name = name
                break
        if kpi_name is None:
            continue

        for col_idx, year in year_map.items():
            if col_idx >= len(tds):
                continue
            valor = _parse_decimal(tds[col_idx].get_text(strip=True))
            if valor is None:
                continue
            records.append({
                "nif_entidad":      nif,
                "ejercicio":        year,
                "kpi":              kpi_name,
                "valor":            valor,
                "unidad":           "EUR",
                "fuente_cuenta":    "rendiciondecuentas_cg",
                "odmgr_dataset_id": None,
            })

    return records


def _parse_balance(
    session: requests.Session,
    url: str,
    nif: str,
    ejercicio: int,
) -> list[dict]:
    """
    Parses the Balance sheet (activo/pasivo section totals).

    Balance columns: Activo | Nota | Ejercicio Actual | Ejercicio Anterior
    (Note: 'Activo' is the label column; indices shift by 1 compared to other tables)
    """
    return _parse_two_year_table(
        session, url, nif, ejercicio, _BAL_ROWS,
    )


def _parse_decimal(s: str) -> Optional[Decimal]:
    """Converts Spanish-locale number string to Decimal. Returns None on failure."""
    s = s.strip().replace("\xa0", "").replace(".", "").replace(",", ".")
    if not s or s in ("-", "—", ""):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

# CityDashboard

> **Panel de Control Municipal** modular para ciudades españolas. Integra rigor presupuestario, sostenibilidad financiera, recursos humanos, coste de servicios y datos socioeconómicos en un único cuadro de mando con semáforos legales (LOEPSF, Ley 15/2010).

Configurado de fábrica para **Jerez de la Frontera**. Adaptable a cualquier municipio español cambiando las variables `CITY_*` en `.env`.

[![CI](https://github.com/PepeluiMoreno/JerezBudgetAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/PepeluiMoreno/JerezBudgetAPI/actions/workflows/ci.yml)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Fuentes de datos públicas                                                  │
│  transparencia.jerez.es  ·  rendiciondecuentas.es  ·  CONPREL  ·  INE/SEPE │
└───────────────┬───────────────────────────────────┬─────────────────────────┘
                │ XLSX / PDF                         │ REST / XBRL / XLSX
                ▼                                   ▼
┌───────────────────────────────┐   ┌───────────────────────────────────────┐
│   OpenDataManager (ODM)       │   │  ETL directo CityDashboard             │
│   puerto 8000                 │   │  (Celery · queue etl)                  │
│                               │   │                                        │
│  Fetchers:                    │   │  · Ejecución presupuestaria XLSX       │
│  · REST, HTML, FileDownload…  │   │  · CONPREL (Hacienda, mdbtools)        │
│  · PDF_TABLE (pdfplumber)     │   │  · Cuenta General (rendiciondecuentas) │
│  · PDF_PAGE + script Jerez    │   │  · seed_entities.py                    │
│                               │   │                                        │
│  Recursos Jerez configurados: │   │  MinIO  ←  caché ficheros fuente       │
│  · jerez_pmp_mensual          │   └──────────────────┬────────────────────┘
│  · jerez_morosidad_trimestral │                      │
│  · jerez_deuda_financiera     │   webhook HMAC-SHA256 │
│  · jerez_cesel                │   POST /webhooks/odmgr│
│                               │◄─────────────────────┘
└───────────────────────────────┘
                │ webhook HMAC-SHA256
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FastAPI + Strawberry GraphQL  (puerto 8015)                                │
│                                                                             │
│  /graphql   ·   /admin (Jinja2+HTMX)   ·   /webhooks/odmgr                 │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │
                            ▼
                    PostgreSQL 16
         (tablas por capa — ver sección Modelo de datos)
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Vue 3 SPA (Vite · ECharts · Tailwind)   puerto 8080                        │
│  Módulos: Rigor · Recaudación · Sostenibilidad · PMP · Deuda                │
│           RPT · Coste Servicios · Comparativa · Dashboard ejecutivo         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| API + GraphQL | FastAPI 0.115 · Strawberry · Pydantic v2 |
| Base de datos | PostgreSQL 16 · SQLAlchemy 2.0 async · Alembic |
| ETL / tareas | Celery 5 · Redis · httpx · openpyxl · pdfplumber |
| Adquisición de datos | OpenDataManager (ODM) — fetchers configurables |
| Frontend | Vue 3 · Vite · graphql-request · ECharts · Tailwind CSS |
| Storage | MinIO (S3-compatible) |
| Infraestructura | Docker Compose · Traefik v3 · Let's Encrypt |

---

## Arranque rápido (desarrollo)

```bash
git clone git@github.com:PepeluiMoreno/JerezBudgetAPI.git
cd JerezBudgetAPI
cp .env.example .env          # editar passwords y CITY_* si se cambia la ciudad
make dev                      # levanta todos los servicios + migraciones
make seed                     # catálogo INE (~8.131 municipios)
make load-conprel             # CONPREL histórico (~25 min)

# Sembrar entidades municipales (Ayto + empresas + grupo consolidado)
docker exec citydashboard_worker celery -A tasks.celery_app call \
    tasks.seed_entities.seed_municipal_entities

# Cargar histórico ejecución presupuestaria (2020-2026)
docker exec citydashboard_worker celery -A tasks.celery_app call \
    tasks.etl_tasks.discover_and_ingest --kwargs '{"years": [2020,2021,2022,2023,2024,2025]}'
```

| Servicio | URL |
|---|---|
| Vue SPA (frontend) | http://localhost:8080 |
| GraphQL + GraphiQL | http://localhost:8015/graphql |
| Admin | http://localhost:8015/admin |
| Flower (Celery) | http://localhost:5555 |
| MinIO | http://localhost:9001 |

---

## Fuentes de datos

### ETL directo (CityDashboard)

| Fuente | Contenido | Granularidad |
|---|---|---|
| `transparencia.jerez.es` — XLSX ejecución | Gastos e ingresos presupuestarios | Mensual (snapshot) |
| `rendiciondecuentas.es` — XBRL | Cuenta General: balance, liquidación, tesorería, ratios | Anual |
| CONPREL — Hacienda | Liquidaciones de 8.000+ municipios | Anual |
| INE Nomenclátor | Padrón y superficie de todos los municipios | Anual |

### Vía OpenDataManager (ODM)

ODM actúa como capa de adquisición de datos. Descarga, normaliza y entrega los datos a CityDashboard mediante webhook HMAC. CityDashboard no accede directamente a las fuentes externas para estos recursos.

| Resource ODM | Fetcher | Contenido | Target |
|---|---|---|---|
| `jerez_pmp_mensual` | `PDF_TABLE` | PMP mensual Ayto + entidades dependientes (Ley 15/2010) | `cuenta_general_kpis` (periodo='01'–'12') |
| `jerez_morosidad_trimestral` | `PDF_TABLE` | Pagos dentro/fuera de plazo, facturas pendientes, intereses | `cuenta_general_kpis` (periodo='T1'–'T4') |
| `jerez_deuda_financiera` | `PDF_TABLE` | Deuda financiera a 31-dic: privada, ICO, total | `cuenta_general_kpis` (periodo='') |
| `jerez_cesel` | `FILE_DOWNLOAD` (XLSX) | Coste efectivo de servicios municipales | `cesel_kpis` |
| INE Padrón Municipal | `REST` | Población de todos los municipios | `ine_padron_municipal` |
| Hacienda Deuda Viva | `FILE_DOWNLOAD` | Deuda viva de entidades locales | `cuenta_general_kpis` |

---

## Integración con OpenDataManager: inyección de script por ciudad

### Patrón PDF_TABLE

Para fuentes en PDF con estructura tabular predecible (PMP, morosidad, deuda), ODM usa el fetcher `PDF_TABLE`:

```python
# Resource configurado en ODM para Jerez
Resource(
    name        = "jerez_pmp_mensual",
    fetcher     = "PDF_TABLE",        # app/fetchers/pdf_table.py
    target_table= "jerez_pmp_mensual",
    params = [
        ("url_template",
         "https://transparencia.jerez.es/infopublica/economica"
         "/c-deuda/{year}/pmp/Informe_PMP_{year}_{month}.pdf"),
        ("granularity", "monthly"),
        ("year_from",   "2020"),
        ("year_to",     "2025"),
    ]
)
```

`PdfTableFetcher` itera el rango de años/meses, descarga cada PDF, extrae su primera tabla con `pdfplumber` y emite una fila de dict por fila de la tabla, enriquecida con `_year` y `_month`.

### Patrón SCRIPT (para fuentes con lógica de extracción específica de ciudad)

Cuando la extracción requiere lógica propia — PDFs con formato no estándar, portales con sesión, APIs con autenticación — el fetcher `SCRIPT` delega en un módulo Python inyectado como parámetro del Resource:

```python
# Resource configurado en ODM — ejemplo Jerez Cuenta General
Resource(
    name    = "jerez_cuenta_general",
    fetcher = "SCRIPT",           # app/fetchers/script.py
    params  = [
        ("script_module", "scripts.jerez.parsers.cuenta_general"),  # ← ciudad
        ("function_name", "run"),                                    # opcional, default
        ("ejercicio",     "2023"),   # pasado al script como params["ejercicio"]
        ("nif",           "P1102000E"),
    ]
)
```

El script del parser (`scripts/jerez/parsers/cuenta_general.py`) implementa el contrato:

```python
def run(params: dict) -> list[dict]:
    """
    Recibe todos los params del Resource.
    Devuelve lista de dicts planos y serializables a JSON.
    """
    ejercicio = int(params["ejercicio"])
    nif       = params["nif"]
    # ... lógica de scraping específica de Jerez ...
    return [{"nif_entidad": nif, "ejercicio": ejercicio, "kpi": "rtgg", "valor": 4543800}, ...]
```

El fetcher gestiona el ciclo de vida completo: importación dinámica del módulo, validación del tipo de retorno y normalización a JSON. El resto del pipeline ODM (staging JSONL → dataset versionado → webhook HMAC → CityDashboard) es idéntico al de cualquier otro fetcher.

Para adaptar a otra ciudad basta con cambiar `script_module` a `scripts.cordoba.parsers.cuenta_general` — sin tocar el core de ODM ni CityDashboard.

### Adaptación a otro municipio

Para adaptar CityDashboard a otro municipio:

1. Cambiar variables `CITY_*` en `.env`:
   ```bash
   CITY_NAME="Córdoba"
   CITY_NIF="P1402000J"
   CITY_INE_CODE="14021"
   CITY_ID_ENTIDAD=1234
   ```

2. Ejecutar `make seed` + `seed_municipal_entities` — puebla `municipal_entities` desde rendiciondecuentas.es.

3. Configurar resources ODM equivalentes para el nuevo portal de transparencia (mismos fetchers, diferentes `url_template`).

4. Si el PDF tiene un formato diferente, escribir el script de parseo en `scripts/{ciudad}/parsers/`.

---

## Modelo de datos (capas)

```
Capa 1 — Presupuesto Jerez
  fiscal_years → budget_snapshots → budget_lines
  rigor_metrics · budget_modifications

Capa 2 — Nacional (CONPREL + INE)
  municipalities · municipal_budgets · municipal_budget_chapters
  municipal_population · peer_groups · peer_group_members

Capa 3 — Socioeconómico (ODM)
  ine_padron_municipal

Capa 4 — Sostenibilidad y KPIs financieros
  cuenta_general_kpis   (nif_entidad, ejercicio, kpi, periodo)
    periodo: '' anual | '01'-'12' mensual | 'T1'-'T4' trimestral
  cesel_kpis            (nif_entidad, ejercicio, servicio, kpi)
  etl_validation_exceptions

Capa 5 — Infraestructura de análisis
  municipal_entities    (catálogo corporación municipal, genérico)
  kpi_thresholds        (umbrales LOEPSF / Ley 15/2010 para semáforos)
  rpt_puestos           (RPT — pendiente S13)
```

### `municipal_entities` — arquitectura multi-entidad

Almacena el catálogo de entidades de la corporación municipal (ayuntamiento, OPAs, empresas municipales, fundaciones, consorcio, grupo consolidado) sin hardcodear ningún nombre. Se puebla desde `rendiciondecuentas.es` de forma genérica.

```
nif            — PK. NIF real (P...) o sintético G{ine_code}0 para grupo consolidado
tipo           — ayto | opa | empresa | fundacion | consorcio | grupo
ine_code       — municipio al que pertenece
alias_fuentes  — JSON: {"pmp_pdf": "nombre exacto en el PDF", "cesel": "..."}
                 permite resolver nombre→NIF sin lógica específica por ciudad
```

El NIF del grupo consolidado se calcula: `f"G{ine_code}0"` (ej: `G110200` para Jerez).

### `kpi_thresholds` — semáforos con base legal

Cada KPI del cuadro de mando tiene umbrales precargados con su norma:

| KPI | Amarillo | Rojo | Base legal |
|---|---|---|---|
| `pmp_ayto` | > 30 días | > 60 días | Ley 15/2010, art. 5 |
| `remanente_tesoreria_gastos_generales` | — | < 0 | LOEPSF art. 3 |
| `ratio_deuda_ingresos_corrientes` | > 0,75 | > 1,10 | LOEPSF art. 13 |
| `tasa_ejecucion_gasto` | < 70% | < 50% | Buena práctica |
| `ratio_pagos_fuera_plazo` | > 20% | > 40% | Ley 15/2010 |

---

## Módulos del dashboard (Vue 3 SPA)

| Módulo | Ruta | Estado | Sprint |
|---|---|---|---|
| Rigor presupuestario | `/financiero/rigor` | ✅ Operativo | S01–S09 |
| Recaudación e ingresos | `/financiero/recaudacion` | ✅ Operativo | S10 |
| Sostenibilidad (Cuenta General) | `/financiero/sostenibilidad` | ✅ Operativo | S10 |
| Comparativa CONPREL | `/financiero/comparativa` | ✅ Operativo | S07 |
| Explorador presupuestario | `/financiero/explorador` | ✅ Operativo | S07 |
| PMP mensual (Ley 15/2010) | `/financiero/pmp` | 🔧 En construcción | S11 |
| Deuda y Morosidad | `/financiero/deuda-morosidad` | 📋 Planificado | S12 |
| Recursos Humanos (RPT) | `/rrhh` | 📋 Planificado | S13 |
| Coste Efectivo de Servicios | `/financiero/coste-servicios` | 📋 Planificado | S14 |
| Cuadro de Mando Ejecutivo | `/` | 📋 Planificado | S15 |
| Contratación pública (PLACE) | `/contratacion` | 📋 Planificado | S16 |
| Subvenciones (BDNS) | `/subvenciones` | 📋 Planificado | S17 |
| Cartas de Servicios (ChoS) | `/servicios` | 📋 Planificado | S18 |

---

## Roadmap de sprints

- [x] **S01–S09** Núcleo presupuestario: ETL Jerez, CONPREL, OLAP, rigor, comparativa, UI inicial
- [x] **S10** ODM integration · Cuenta General scraper · Vue 3 SPA con 7 secciones
- [x] **S0** *(adaptación)* `PdfTableFetcher` en ODM · `municipal_entities` · `periodo` en KPIs · `kpi_thresholds` · webhook handlers para PMP/morosidad/deuda/CESEL
- [ ] **S11** Módulo PMP mensual — GraphQL + Vista Vue con semáforo Ley 15/2010
- [ ] **S12** Módulo Deuda y Morosidad — serie histórica + morosidad trimestral
- [ ] **S13** Módulo RPT — plantilla + KPIs coste/habitante, ratio vacantes
- [ ] **S14** Módulo Coste Efectivo de Servicios — CESEL, coste unitario, benchmarking
- [ ] **S15** Cuadro de Mando Ejecutivo — 10-15 KPIs críticos, semáforos, sparklines 36 meses
- [ ] **S16** Contratación pública (PLACE via ODM)
- [ ] **S17** Subvenciones (BDNS via ODM)
- [ ] **S18** Cartas de Servicios (integración ChoS)

---

## Grupo de comparación (benchmarking)

Jerez (213k hab.) se compara automáticamente con:
- Municipios de **180k–250k habitantes** de España (≈15 ciudades)
- Media **Andalucía** (ponderada por población)
- Media **nacional** (ponderada por población)

El grupo se recalcula anualmente con el Padrón Municipal del INE vía ODM.

---

## Licencia

[AGPL-3.0](LICENSE) · © 2026 [PepeluiMoreno](https://github.com/PepeluiMoreno)

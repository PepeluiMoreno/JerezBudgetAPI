# JerezBudgetAPI — Handoff

## Qué es esto

API + Dashboard para analizar el **rigor presupuestario** del Ayuntamiento de Jerez de la Frontera y la **situación socioeconómica** de la ciudad, comparándola con municipios de tamaño similar y con medias provinciales, autonómicas y nacionales.

Dos preguntas principales:
1. **¿Gestiona bien el ayuntamiento?** — Precisión presupuestaria, deuda, PMP, RTGG.
2. **¿Cómo está la ciudad?** — Paro, renta, demografía, turismo, benchmarking.

---

## Stack

```
FastAPI (8015)  ←→  PostgreSQL 16  ←→  MinIO (9000)
     ↑                    ↑
Celery workers        Alembic
     ↑
  Redis (6379)
     ↑
Dash dashboard (8050)   ←→   OpenDataManager / odmgr_app (8000)
```

**Celery queues**: `etl` (ingestión XLSX + CONPREL + Cuenta General), `metrics` (cálculo rigor)

---

## Historial de sprints

| Sprint | Commit | Contenido |
|--------|--------|-----------|
| S01 | `f6d1c2e` | Fundamentos: modelos ORM, FastAPI esqueleto, docker-compose, Alembic base |
| S02a | `cff2b22` | Panel admin Jinja2+HTMX — gestión de modificaciones presupuestarias |
| S02b | `c276cca` | ETL completo: scraper transparencia.jerez.es, parser XLSX, loader, Celery, métricas IPP/ITP/ITR |
| S03 | `a242efe` | GraphQL (Strawberry) completo + migración Alembic automatizada |
| S04 | `73bc074` | Modelo BD nacional: catálogo INE municipios, presupuestos CONPREL, peer groups |
| S05 | `3927501` | ETL CONPREL completo: descarga MDB Hacienda → PostgreSQL (8.000 municipios × 15 años) |
| S06 | `290ef9f` | Capa OLAP babbage: cubos OLAP vía `/api/3/cubes/` (jerez-rigor, jerez-detail) |
| S07 | `d62bb72` | Dashboard Dash: tres vistas (`/rigor`, `/explorador`, `/comparativa`) |
| S08 | `e2b485f` | Producción: Makefile, health checks, configuración CI/CD, nginx |
| S09 | `c2791f3`–`236a6d4` | Estabilización: arranque stack, corrección ETL CONPREL + INE, event loop fix |
| **S10** | **`2387bec`** | **ODM integration + Cuenta General scraper (ver detalle abajo)** |

---

## Estado actual (S10 completado)

### Lo que funciona hoy

| Capa | Qué hay | Endpoint / tabla |
|------|---------|-----------------|
| API REST | Health, admin, OLAP, webhooks ODM | `/health`, `/admin/*`, `/api/3/*`, `/webhooks/odmgr` |
| GraphQL | Consulta presupuestos Jerez + CONPREL nacional | `/graphql` |
| ETL Jerez | Scraper + parser XLSX ejecución presupuestaria 2020-2026 | Celery `etl` queue |
| ETL CONPREL | 8.000 municipios × 15 años, MDB Hacienda | `municipal_budgets`, `municipalities` |
| ETL INE Padrón | Descarga masiva padrón municipal (todos municipios) | `ine_padron_municipal` |
| Cuenta General | Scraper rendiciondecuentas.es, 44 KPIs × 7 años (2016-2022) | `cuenta_general_kpis` |
| Deuda Viva | Sync desde ODM webhook (Hacienda XLSX) | `cuenta_general_kpis` kpi=`deuda_viva` |
| Dashboard | `/rigor`, `/explorador`, `/comparativa` | Puerto 8050 |

### Modelo de datos completo

```
── Capa 1: Presupuesto Jerez ──────────────────────────────────────────
fiscal_years              ← ejercicios 2020-2026
budget_snapshots          ← un snapshot por XLSX (phase: expense / revenue)
budget_lines              ← líneas presupuestarias
economic/functional/organic_classification
rigor_metrics             ← IPP, ITP, ITR, score global por ejercicio

── Capa 2: Nacional (CONPREL + INE) ──────────────────────────────────
municipalities            ← catálogo INE con código, nombre, provincia, CCAA
municipal_budgets         ← liquidaciones CONPREL (ingresos/gastos totales)
municipal_budget_chapter  ← desglose por capítulo
municipal_budget_program  ← desglose por programa
peer_groups               ← grupos de pares (180k-250k hab., Andalucía, nacional)
municipal_population      ← población CONPREL (para cálculos per cápita en CONPREL)

── Capa 3: Socioeconómico (ODM + scrapers) ───────────────────────────
ine_padron_municipal      ← padrón INE todos municipios (vía ODM webhook)
cuenta_general_kpis       ← KPIs sostenibilidad (ver tabla completa abajo)
```

### KPIs en `cuenta_general_kpis` (fuente `rendiciondecuentas_cg`)

| KPI | Descripción | Unidad |
|-----|-------------|--------|
| `remanente_tesoreria_gastos_generales` | RTGG — indicador clave sostenibilidad | EUR |
| `remanente_tesoreria_total` | Remanente de tesorería total (I) | EUR |
| `activo_total` | Total activo balance | EUR |
| `patrimonio_neto` | Patrimonio neto (negativo en Jerez) | EUR |
| `pasivo_corriente` | Pasivo corriente | EUR |
| `pasivo_no_corriente` | Pasivo no corriente (deuda LP) | EUR |
| `activo_corriente` | Activo corriente | EUR |
| `fondos_liquidos` | Fondos líquidos (tesorería) | EUR |
| `derechos_pendientes_cobro` | Derechos pendientes de cobro | EUR |
| `ingresos_gestion_ordinaria_cr` | Total ingresos gestión ordinaria | EUR |
| `gastos_gestion_ordinaria_cr` | Total gastos gestión ordinaria | EUR |
| `resultado_gestion_ordinaria` | Ahorro/desahorro ordinario | EUR |
| `resultado_neto_ejercicio` | Resultado económico-patrimonial neto | EUR |
| `liquidez_inmediata` | Fondos líquidos / Pasivo corriente | RAT |
| `liquidez_corto_plazo` | (Fondos + Dtos cobro) / PC | RAT |
| `liquidez_general` | Activo corriente / Pasivo corriente | RAT |
| `endeudamiento` | Pasivo total / Activo total | RAT |
| `endeudamiento_habitante` | (PC + PNC) / Habitantes | EUR/hab |
| `pmp_acreedores` | Periodo medio de pago a acreedores | días |
| `periodo_medio_cobro` | Periodo medio de cobro | días |
| `cobertura_gastos_corrientes` | Gastos / Ingresos gestión ordinaria | RAT |
| `cash_flow` | Indicador cash-flow | RAT |
| `ratio_ingresos_tributarios` | Ingresos tributarios / Total | RAT |
| `ratio_transferencias_recibidas` | Transferencias / Total ingresos | RAT |
| `ratio_gastos_personal` | Gastos personal / Total gastos | RAT |
| ... (+ 20 más) | | |

También en `cuenta_general_kpis` (fuente `hacienda_deuda_viva`):
- `deuda_viva` — deuda financiera formal (Hacienda InformacionEELLs)

---

## KPIs implementados — rigor presupuestario

| Índice | Fórmula | Fuente |
|--------|---------|--------|
| **IPP** Precisión | Obligaciones / Créditos iniciales | ETL Jerez |
| **ITP** Puntualidad | 0 si prorrogado; 1 − (días_retraso/365) | ETL Jerez |
| **ITR** Transparencia | Docs publicados / esperados | ETL Jerez |
| Score global | IPP×0.4 + ITP×0.3 + ITR×0.3 | calculado |
| Tasa ejecución gasto | Obligaciones / Créditos definitivos | ETL Jerez |
| Tasa ejecución ingreso | Derechos / Previsiones definitivas | ETL Jerez |

---

## Roadmap — sprints pendientes

### S11 — API Sostenibilidad + KPIs per cápita
**Objetivo:** exponer los datos de Cuenta General vía API y calcular KPIs per cápita.

- [ ] `GET /api/sostenibilidad/jerez` — serie histórica de todos los KPIs de `cuenta_general_kpis`
- [ ] `GET /api/sostenibilidad/comparativa` — benchmark Jerez vs grupo de pares (deuda/hab, RTGG, PMP)
- [ ] Cálculo €/habitante para KPIs monetarios (usando `ine_padron_municipal`)
- [ ] GraphQL: queries `sostenibilidadKpis(nif, ejercicio)` y `comparativaSostenibilidad`

**Datos necesarios:** `cuenta_general_kpis` (✅ cargado), `ine_padron_municipal` (✅ disponible vía ETL)

---

### S12 — Dashboard Sostenibilidad
**Objetivo:** nueva vista Dash `/sostenibilidad` con evolución temporal y benchmarking.

- [ ] `dashboard/pages/sostenibilidad.py`
  - Tarjetas RTGG, Deuda viva, PMP, Liquidez (año más reciente)
  - Gráfico de líneas: evolución 2016-2022 de RTGG, deuda, resultado neto
  - Benchmark: Jerez vs grupo de pares en €/hab (deuda, RTGG)
  - Semáforo RAL-LOEPSF: regla gasto, deuda/PIB, estabilidad presupuestaria
- [ ] `dashboard/pages/cuenta_general.py`
  - Balance simplificado año a año (activo, pasivo, patrimonio neto)
  - Cuenta de resultados: ingresos/gastos ordinarios, resultado neto
  - Indicadores oficiales IndFinYPatri completos

---

### S13 — Dashboard Socioeconómico (datos ODM vía GraphQL)
**Objetivo:** nueva vista Dash `/socioeconomico` con datos de ciudad desde ODM.

- [ ] Conectar dashboard con ODM GraphQL para:
  - Paro registrado SEPE por municipio (serie histórica)
  - Atlas de Distribución de Renta INE (renta neta media)
  - Encuesta Ocupación Hotelera INE (pernoctaciones turísticas)
- [ ] Vista `/socioeconomico`: comparativa Jerez vs grupo de pares en paro, renta, turismo
- [ ] Seedear datos socioeconómicos en ODM (completar fetchers SEPE, INE renta, EOH)

---

### S14 — Informe PDF + exportación
**Objetivo:** generar informes descargables.

- [ ] `GET /api/informe/jerez/{year}` — PDF con resumen completo (rigor + sostenibilidad + socioeco)
- [ ] Exportación de cubos a CSV/XLSX desde el explorador del dashboard

---

## Operaciones habituales

```bash
# Recargar ETL Jerez completo
docker compose exec api python -c "
from tasks.etl_tasks import discover_and_ingest
discover_and_ingest.apply_async(queue='etl')
"

# Recargar Cuenta General histórico (2016-2022)
docker compose exec worker celery -A tasks.celery_app call \
  tasks.cuenta_general_tasks.load_historical_cg

# Recargar CONPREL un año concreto
docker compose exec worker celery -A tasks.celery_app call \
  tasks.conprel_tasks.ingest_conprel_year --kwargs '{"year": 2023}'

# Ver workers activos
docker compose exec worker celery -A tasks.celery_app inspect active

# Reseed ODM (tras cambios en seed_data.py)
docker compose -f /opt/docker/apps/opendatamanager/docker-compose.yml \
  exec odmgr_app python seed_data.py

# BD
docker compose exec db psql -U jerezbudget -d jerezbudget
```

---

## Decisiones técnicas relevantes

| Problema | Solución |
|----------|----------|
| Phase collision snapshots | `phase="executed_expense"/"executed_revenue"` en constraint `uq_snapshot_year_date_phase` |
| Event loop en Celery | Cada tarea llama `engine.dispose()` + `asyncio.run()` propio; no reutiliza el engine global |
| MinIO vs idempotencia BD | MinIO cachea HTTP (evita re-download); SHA256 en `BudgetSnapshot` controla duplicados en BD |
| GraphQL incompatibilidad | `strawberry 0.249` incompatible con `pydantic 2.11+`; startup hace try/except, API arranca igual |
| Double JSESSIONID en scraper | `rendiciondecuentas.es` usa dos cookies JSESSIONID en paths distintos; `httpx` da `CookieConflict`; se usa `requests` |
| RTGG no calculable desde CONPREL | Requiere caja + derechos/obligaciones no presupuestarias → scraped directamente del portal Tribunal de Cuentas |
| Deuda Viva (Hacienda) | XLSX público `InformacionEELLs`; miles€ → euros (×1000); código INE 5 dígitos como clave |

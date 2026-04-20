# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**CityDashboard** — Panel de Control Municipal modular para ciudades españolas.
Parametrizado por municipio vía variables `CITY_*` en `.env`. Actualmente configurado para Jerez de la Frontera (`CITY_NIF=P1102000E`, `CITY_INE_CODE=11020`).

El repo sigue llamándose `JerezBudgetAPI` en disco/GitHub pero el proyecto se denomina **CityDashboard** en el código fuente.

## Commands

```bash
# Desarrollo — todo en Docker
make dev               # up + migraciones (primera vez)
make up / make down
make logs              # todos los servicios
make shell             # bash en el contenedor API
make db-shell          # psql directo

# Base de datos
make migrate           # alembic upgrade head
make migrate-down      # alembic downgrade -1

# Tests y calidad
make test              # pytest en contenedor
make test-fast         # pytest -x (para en el primer fallo)
make lint              # ruff check .
make format            # ruff format .

# ETL manual
make load-jerez        # descubre + ingesta XLSX transparencia.jerez.es
make load-conprel      # CONPREL histórico (~25 min)
make rebuild-peer      # recalcula grupos de pares
make seed              # catálogo INE ~8.131 municipios
```

Un test individual:
```bash
docker compose run --rm api pytest tests/test_metrics.py::test_rigor_score -v
```

Alembic nueva migración:
```bash
docker compose run --rm api alembic revision --autogenerate -m "descripcion"
```

Invocar tarea Celery manualmente:
```bash
docker exec citydashboard_worker celery -A tasks.celery_app call \
    tasks.etl_tasks.discover_and_ingest --kwargs '{"years": [2025]}'
```

## Servicios y puertos

| Servicio | URL |
|---|---|
| Vue SPA (frontend) | http://localhost:8080 |
| GraphQL + GraphiQL | http://localhost:8015/graphql |
| Admin (Jinja2+HTMX) | http://localhost:8015/admin |
| OLAP REST legacy | http://localhost:8015/api/3/cubes/ |
| Flower (Celery) | http://localhost:5555 |
| MinIO console | http://localhost:9001 |

## Architecture

### Stack
- **Backend**: FastAPI + Strawberry GraphQL + SQLAlchemy 2.0 async + Alembic
- **Frontend**: Vue 3 SPA (Vite + graphql-request + ECharts + Tailwind)
- **ETL**: Celery 5 (queue `etl`) + Redis + MinIO (caché de ficheros fuente)
- **Admin**: Jinja2 + HTMX (sin cambios planeados)
- **BD**: PostgreSQL 16 con `citydashboard_db` / usuario `citydashboard`

### Capas de datos (5 capas)

```
Capa 1 — Presupuesto Jerez (transparencia.jerez.es)
  fiscal_years → budget_snapshots → budget_lines
  rigor_metrics · budget_modifications
  ETL: etl/scraper.py → etl/downloader.py → etl/loader.py
       tasks/etl_tasks.py (discover_and_ingest → ingest_file → compute_metrics)

Capa 2 — Nacional (CONPREL Hacienda + INE Nomenclator)
  municipalities · municipal_budgets · municipal_budget_chapters
  municipal_budget_programs · municipal_population
  peer_groups · peer_group_members
  ETL: etl/conprel/ · tasks/conprel_tasks.py

Capa 3 — Socioeconómico (OpenDataManager via webhook)
  ine_padron_municipal · (ine_renta, sepe_paro, ine_eoh vía ODM GraphQL)
  Webhook: POST /webhooks/odmgr (HMAC verificado)
  Sync: services/odmgr_sync.py

Capa 4 — Sostenibilidad (rendiciondecuentas.es + transparencia.jerez.es)
  cuenta_general_kpis (44 KPIs por año: balance, CREPA, RT, IndFinYPatri)
  etl_validation_exceptions (discrepancias entre fuentes)
  ETL: services/cuentas_scraper.py · services/cg_ayto_scraper.py (pendiente)
       tasks/cuenta_general_tasks.py · tasks/cgkpi_upsert.py

Capa 5 — RPT (pendiente S11)
  rpt_puestos
```

### GraphQL (`gql/`)

- **`gql/schema.py`** — schema raíz con todas las queries/mutations; combina todos los resolvers
- **`gql/types.py`** — tipos Strawberry
- **`gql/resolvers/`** — un fichero por dominio: `fiscal_years`, `budget_lines`, `metrics`, `modifications`, `modifications_summary`, `snapshots`, `sostenibilidad`, `etl`

El contexto GraphQL inyecta `db: AsyncSession` vía `info.context["db"]`.

### ETL pipeline (Capa 1)

```
discover_and_ingest (Celery)
  └── etl/scraper.py → descubre DiscoveredFile[]
  └── etl/downloader.py → descarga + calcula SHA256 + sube a MinIO
  └── ingest_file (Celery) — por cada fichero nuevo
       └── etl/parsers/xlsx_execution.py → BudgetLineRecord[]
       └── etl/loader.py → upsert en BD (idempotente por SHA256)
  └── compute_metrics (Celery) → recalcula rigor_metrics
```

### Cuenta General KPI upsert

Todos los ETL de sostenibilidad deben pasar por `tasks/cgkpi_upsert.py:validate_and_upsert_cgkpis()`. Nunca INSERT directo. La función detecta discrepancias entre fuentes y las registra en `etl_validation_exceptions`.

Prioridad de fuentes (menor número = más autoritativa): definida en `models/socioeconomic.py:source_priority()`.

### Frontend (`frontend/src/`)

```
views/
  financiero/
    RigorView.vue          ← rigor presupuestario (datos de CG + liquidaciones)
    SostenibilidadView.vue ← Cuenta General KPIs + liquidaciones híbrido
    ComparativaView.vue    ← CONPREL peer groups
    ExploradorView.vue     ← explorador líneas presupuestarias
  CiudadView.vue · RecursosHumanosView.vue · etc.
api/
  client.js     ← graphql-request setup (VITE_GRAPHQL_URL)
  financiero.js ← todas las queries GraphQL del módulo financiero
components/
  KpiCard.vue   ← tarjeta con valor, badge, modal info y modal gráfico de tendencia
                   prop `trendData: [{label, value, partial?}]` — partial=true rompe la línea
                   prop `trendSource` — fuente en el footer del modal de evolución
```

### Parametrización por ciudad

`app/config.py:Settings` lee `CITY_*` del `.env`. Los resolvers y ETL usan `get_settings().city_nif` como clave de entidad. Para adaptar a otro municipio: cambiar las variables `CITY_*` en `.env` y ejecutar `make seed` + `make load-conprel`.

### Patrones de código

- **Async**: todos los resolvers GraphQL y accesos a BD son `async`. Las tareas Celery son síncronas pero llaman `asyncio.run(...)` internamente (no mezclar event loops).
- **Importes**: `Numeric(16,2)` — nunca `float` para cantidades monetarias.
- **Upsert**: `pg_insert(...).on_conflict_do_update(...)` de `sqlalchemy.dialects.postgresql`.
- **Engine disposal en Celery**: llamar `await engine.dispose()` antes de `asyncio.run()` en tareas que crean un nuevo event loop.
- **Logging**: `structlog` en Python, `console` en dev, `json` en producción.

## Database notes

El volumen Postgres (`jerezbudgetapi_pg_data`) fue inicializado con usuario `jerezbudget` / DB `jerezbudget`. Tras la migración a CityDashboard:
- Usuario: `citydashboard` (permisos concedidos sobre la DB renombrada)  
- DB: `citydashboard_db` (renombrada desde `jerezbudget`)
- El usuario `jerezbudget` (superuser) sigue existiendo para operaciones de administración

## Sprint status (2026-04-20)

- **S10 completado**: ODM integration, Cuenta General scraper (rendiciondecuentas.es), ETL validation exceptions, Vue SPA operativa con 7 secciones
- **S11 en curso**: RPT (Relación de Puestos de Trabajo) — modelo, ETL, GraphQL
- **ODM resource declarations**: `docs/odm_resources/gestion_financiera.json` (8 recursos, 6 activos) + `seed_resources.py` + `docs/odm_integration.md` + `docs/gestion_financiera.md` (7 secciones con KPIs)
- **Renombrado pendiente**: carpeta `JerezBudgetAPI/` → `CityDashboard/`, repo GitHub, docker-compose service names (parcialmente hecho)
- **Scraper PDF ayuntamiento** (`services/cg_ayto_scraper.py`): stub implementado, pendiente parseo real de PDFs de transparencia.jerez.es
- **ODM Sprint 2 pendiente**: recursos PDF_TABLE para morosidad (2022-2025), deuda (2021-2023,2025), CESEL (2022-2024), liquidaciones anuales

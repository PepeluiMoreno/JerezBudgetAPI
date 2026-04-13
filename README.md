# JerezBudget API

> Sistema de análisis del **rigor presupuestario municipal** del Ayuntamiento de Jerez de la Frontera, con comparativa contra todos los municipios españoles.

[![CI](https://github.com/PepeluiMoreno/JerezBudgetAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/PepeluiMoreno/JerezBudgetAPI/actions/workflows/ci.yml)

## Arquitectura de 3 capas

```
Capa 1A — JerezBudget API (FastAPI + GraphQL)
  Fuente: transparencia.jerez.es — XLSX mensuales + ETL Celery
  Métricas: IPP (Precisión) · ITP (Puntualidad) · ITR (Transparencia)

Capa 2 — API OLAP babbage (/api/3/cubes/)
  PostgreSQL como sustrato compartido
  4 cubos: municipal-spain · municipal-spain-func · jerez-detail · jerez-rigor

Capa 3 — Dashboard Dash (http://localhost:8050)
  /rigor         Score de rigor histórico con gauges IPP/ITP/ITR
  /comparativa   Jerez vs municipios similares (CONPREL — Ministerio de Hacienda)
  /explorador    Comparativa libre hasta 5 municipios · export CSV
```

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| API + GraphQL | FastAPI 0.115 · Strawberry · Pydantic v2 |
| Base de datos | PostgreSQL 16 · SQLAlchemy 2.0 async · Alembic |
| OLAP | babbage (OpenSpending) adaptado a FastAPI |
| ETL Jerez | Celery 5 · httpx · openpyxl · pdfplumber |
| ETL Nacional | mdbtools · pandas · CONPREL (Ministerio de Hacienda) |
| Dashboard | Plotly Dash 2.x · httpx |
| Storage | MinIO (S3-compatible) |
| Infraestructura | Docker Compose · Traefik v3 · Let's Encrypt |

## Arranque rápido (desarrollo)

```bash
git clone git@github.com:PepeluiMoreno/JerezBudgetAPI.git
cd JerezBudgetAPI
cp .env.example .env        # editar passwords
make dev                    # levanta todo + migraciones
make seed                   # catálogo INE (~8.131 municipios)
make load-ine-pop           # padrón municipal histórico
make load-conprel           # CONPREL 2010-2024 (~25 min)
```

| Servicio | URL |
|----------|-----|
| GraphiQL | http://localhost:8015/graphql |
| Admin modificaciones | http://localhost:8015/admin |
| API OLAP | http://localhost:8015/api/3/cubes/ |
| Dashboard | http://localhost:8050 |
| Flower | http://localhost:5555 |

## Producción (OptiPlex-790 / VPS)

```bash
make prod                   # docker-compose.yml + docker-compose.prod.yml
# Traefik gestiona TLS automáticamente via Let's Encrypt
# budget.${DOMAIN}          → API
# presupuestos.${DOMAIN}    → Dashboard
```

## Queries GraphQL de ejemplo

```graphql
# Score de rigor del año 2025
query { rigorMetrics(fiscalYear: 2025) {
  globalRigorScore precisionIndex timelinessIndex
  expenseExecutionRate approvalDelayDays byChapter
}}

# Desviaciones por capítulo
query { deviationAnalysis(fiscalYear: 2025, by: "chapter") {
  code name deviationPct modificationPct executionRate
}}

# Tendencia histórica
query { rigorTrend(years: [2020,2021,2022,2023,2024,2025]) {
  fiscalYear globalRigorScore isExtension approvalDelayDays
}}
```

## API OLAP (babbage) de ejemplo

```bash
# Ranking andaluz 2023 — €/hab ejecutado
GET /api/3/cubes/municipal-spain/aggregate
  ?drilldown=municipality.name|municipality.ine_code
  &cut=year.fiscal_year:2023|data_type.data_type:liquidation|municipality.ccaa_code:01
  &order=executed_per_capita:desc&pagesize=20

# Jerez vs grupo de pares — capítulo 6 (inversiones)
GET /api/3/cubes/municipal-spain/aggregate
  ?drilldown=municipality.name
  &cut=year.fiscal_year:2023|chapter.chapter:6|chapter.direction:expense
  &order=executed_per_capita:desc

# Descargar Fiscal Data Package (OpenBudgets compatible)
GET /api/3/info/municipal-spain/package
```

## Índices de rigor

| Índice | Fórmula | Peso en score global |
|--------|---------|---------------------|
| IPP Precisión | `100 - \|1 - tasa_ejecución\| × 100` | 50% |
| ITP Puntualidad | `max(0, 100 - días_retraso × 0.5)` | 30% |
| ITR Transparencia | `max(0, 100 - días_publicación × 1.0)` | 20% |
| **Score Global** | `IPP×0.5 + ITP×0.3 + ITR×0.2` | — |

> ⚠️ **2026** es prórroga del presupuesto 2025 → ITP = 0 automáticamente.

## Roadmap completado

- [x] **S01** Fundamentos: ORM, GraphQL mínimo, Docker Compose
- [x] **S02** ETL Jerez: scraper, parser XLSX, Celery, admin HTMX + reconciliación
- [x] **S03** GraphQL completo: filtros, paginación, trend, modificaciones
- [x] **S04** Modelo BD nacional: municipalities, CONPREL tables, peer groups, vista materializada
- [x] **S05** ETL CONPREL: mdbtools parser, loader per-cápita, 2010-2024
- [x] **S06** OLAP babbage: 4 cubos, 5 endpoints, FDP export
- [x] **S07** Dashboard Dash: 3 vistas (rigor, comparativa, explorador)
- [x] **S08** Producción: Traefik TLS, CI/CD GitHub Actions, Makefile

## Fuentes de datos

- **transparencia.jerez.es** — Ejecución mensual por aplicación (XLSX)
- **CONPREL — Ministerio de Hacienda** — Todos los municipios españoles, capítulo económico, 2010-2024 (ficheros .mdb)
- **INE Padrón Municipal** — Población por municipio y año (API JSON)

## Licencia

[AGPL-3.0](LICENSE) · © 2026 [PepeluiMoreno](https://github.com/PepeluiMoreno)

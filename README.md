# JerezBudget API

> Plataforma de análisis del **rigor presupuestario** del Ayuntamiento de Jerez de la Frontera y de la **situación socioeconómica** de la ciudad, con benchmarking automático contra municipios de tamaño similar y medias provinciales, autonómicas y nacionales.

[![CI](https://github.com/PepeluiMoreno/JerezBudgetAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/PepeluiMoreno/JerezBudgetAPI/actions/workflows/ci.yml)

## Arquitectura

```
transparencia.jerez.es          CONPREL (Hacienda)         OpenDataManager (ODM)
       │ XLSX mensual                  │ MDB anual               │ webhook HMAC
       ▼                               ▼                         ▼
  Celery ETL ──────────────────── PostgreSQL 16 ──────────── FastAPI (8015)
  (queue: etl)                         │                         │
  MinIO (caché)                  Alembic + ORM             OLAP babbage
                                       │                    /api/3/cubes/
                                  Dash (8050)
                           /rigor · /comparativa · /explorador
                           /socioeconomico (planificado)
```

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| API + GraphQL | FastAPI 0.115 · Strawberry · Pydantic v2 |
| Base de datos | PostgreSQL 16 · SQLAlchemy 2.0 async · Alembic |
| OLAP | babbage (OpenSpending) adaptado a FastAPI |
| ETL Jerez | Celery 5 · httpx · openpyxl |
| ETL Nacional | mdbtools · pandas · CONPREL |
| Dashboard | Plotly Dash 2.x |
| Storage | MinIO (S3-compatible) |
| Infraestructura | Docker Compose · Traefik v3 · Let's Encrypt |
| Datos abiertos externos | OpenDataManager (ODM) vía webhook |

## Arranque rápido (desarrollo)

```bash
git clone git@github.com:PepeluiMoreno/JerezBudgetAPI.git
cd JerezBudgetAPI
cp .env.example .env        # editar passwords
make dev                    # levanta todo + migraciones
make seed                   # catálogo INE (~8.131 municipios)
make load-conprel           # CONPREL 2010-2024 (~25 min)

# Cargar histórico de ejecución presupuestaria Jerez (2020-2026)
docker compose exec api python -c "
from tasks.etl_tasks import load_historical
load_historical.apply_async(queue='etl')
"
```

| Servicio | URL |
|---|---|
| Dashboard | http://localhost:8050 |
| API OLAP | http://localhost:8015/api/3/cubes/ |
| Admin | http://localhost:8015/admin |
| Docs API | http://localhost:8015/docs |
| Flower (Celery) | http://localhost:5555 |
| MinIO | http://localhost:9001 |

## Fuentes de datos

### Activas
| Fuente | Contenido | Frecuencia |
|---|---|---|
| transparencia.jerez.es | Ejecución presupuestaria (gastos + ingresos) 2020-2026 | Mensual via scraper |
| CONPREL — Hacienda | Liquidaciones de 8.000+ municipios, 2010-2024 | Anual (ficheros .mdb) |

### Vía OpenDataManager (ODM)
| Resource ODM | Contenido | Target table |
|---|---|---|
| INE Padrón Municipal | Población todos los municipios, últimos 10 años | `ine_padron_municipal` |
| INE Atlas Distribución Renta | Renta media por municipio | `ine_renta_municipal` |
| INE Encuesta Ocupación Hotelera | Pernoctaciones por municipio | `ine_eoh_municipal` |
| SEPE Paro Registrado | Parados por municipio, mensual | `sepe_paro_municipal` |
| Hacienda PMP Entidades Locales | Periodo Medio de Pago, mensual | `hacienda_pmp_el` |
| Cuenta General XBRL | Balance, liquidación, tesorería, deuda | `cuenta_general_el` |

## KPIs implementados

### Rigor presupuestario — `/api/3/cubes/jerez-rigor`
| KPI | Fórmula |
|---|---|
| **IPP** Precisión | Obligaciones reconocidas / Créditos iniciales |
| **ITP** Puntualidad | 0 si prórroga; penalización proporcional a días de retraso |
| **ITR** Transparencia | Documentos publicados / esperados |
| **Score Global** | IPP×0.4 + ITP×0.3 + ITR×0.3 |
| Tasa ejecución gasto | Obligaciones / Créditos definitivos |
| Tasa ejecución ingreso | Derechos reconocidos / Previsiones definitivas |
| Tasa modificación | (Créditos definitivos − iniciales) / iniciales |

### KPIs pendientes (requieren ODM)
| KPI | Fuente |
|---|---|
| Gasto / ingreso per cápita por capítulo | INE Padrón |
| PMP (Periodo Medio de Pago a proveedores) | Hacienda-EL |
| Tasa de paro municipal | SEPE |
| Renta media per cápita | INE Atlas Renta |
| Deuda viva / RTGG / ahorro neto | Cuenta General XBRL |
| Dependencia de transferencias | Cap. 4+7 ingresos / total |
| Pernoctaciones per cápita | INE EOH |

## Dashboard

### Vistas actuales
| Ruta | Descripción |
|---|---|
| `/rigor` | Score global + IPP/ITP/ITR + histórico 2020-2026 + ejecución por capítulo |
| `/explorador` | Explorador OLAP libre (jerez-detail) |
| `/comparativa` | Jerez vs municipios similares (CONPREL) |

### Vistas planificadas
| Ruta | Descripción |
|---|---|
| `/socioeconomico` | Paro, renta, demografía, turismo — Jerez vs benchmarks |
| `/sostenibilidad` | Deuda, RTGG, PMP, ahorro neto — evolución y comparativa |
| `/cuenta-general` | Balance y liquidación desglosados año a año |

## Grupo de comparación (benchmarking)

Jerez (213k hab.) se compara automáticamente con:
- Municipios de **180k–250k habitantes** de España (≈15 ciudades)
- Media **Andalucía** (ponderada por población)
- Media **nacional** (ponderada por población)

El grupo se actualiza anualmente con el Padrón Municipal del INE vía ODM.

## API OLAP — ejemplos

```bash
# Rigor Jerez año 2025
GET /api/3/cubes/jerez-rigor/aggregate?drilldown=year.fiscal_year&cut=year.fiscal_year:2025

# Ejecución por capítulo económico
GET /api/3/cubes/jerez-detail/aggregate
  ?drilldown=chapter.chapter|chapter.direction
  &cut=year.fiscal_year:2025|chapter.direction:expense

# Ranking andaluz 2023 — gasto ejecutado per cápita
GET /api/3/cubes/municipal-spain/aggregate
  ?drilldown=municipality.name
  &cut=year.fiscal_year:2023|municipality.ccaa_code:01
  &order=executed_per_capita:desc&pagesize=20
```

## Roadmap

- [x] **S01** ORM, GraphQL, Docker Compose
- [x] **S02** ETL Jerez (scraper, parser XLSX, Celery, admin)
- [x] **S03** GraphQL completo (filtros, paginación, trend)
- [x] **S04** Modelo BD nacional (municipalities, CONPREL, peer groups)
- [x] **S05** ETL CONPREL (mdbtools, loader per-cápita, 2010-2024)
- [x] **S06** OLAP babbage (4 cubos, 5 endpoints, FDP export)
- [x] **S07** Dashboard Dash (3 vistas: rigor, comparativa, explorador)
- [x] **S08** Producción (Traefik TLS, CI/CD, Makefile)
- [x] **S09** Estabilización ETL + UI (fases snapshot, event loop fix, info modales)
- [ ] **S10** ODM integration (webhook receiver, modelos socioeco, KPIs per cápita)
- [ ] **S11** Dashboard socioeconómico (paro, renta, demografía, turismo)
- [ ] **S12** Sostenibilidad financiera (Cuenta General XBRL, deuda, RTGG, PMP)

## Licencia

[AGPL-3.0](LICENSE) · © 2026 [PepeluiMoreno](https://github.com/PepeluiMoreno)

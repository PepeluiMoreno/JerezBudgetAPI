# CityDashboard — Panel de Control Municipal de Jerez

## Qué es esto

Panel de control municipal modular para el Ayuntamiento de Jerez de la Frontera.
Cada sección muestra los indicadores de Jerez y permite compararlos con dos grupos de referencia:

- **Grupo Población**: municipios españoles con 150.000–250.000 habitantes
- **Grupo Superficie**: municipios con término municipal similar al de Jerez (±15%)

---

## Stack

```
Vue 3 SPA (puerto 8080)          ← sidebar + 7 secciones
  ↓ graphql-request
FastAPI (puerto 8015)
  ├── /graphql                   ← API principal (Strawberry)
  ├── /admin/*                   ← Jinja2+HTMX (sin cambios)
  ├── /webhooks/odmgr            ← ODM integration
  └── /health
  ↓
PostgreSQL 16 · Redis · MinIO · Celery
  ↑
OpenDataManager (odmgr_app:8000) ← datos socioeconómicos (INE, SEPE, EOH)
ChoS (repo ChoS)                 ← Cartas de Servicio
```

---

## Secciones del dashboard

| # | Sección | Contenido | Datos Jerez | Comparativa |
|---|---------|-----------|-------------|-------------|
| 1 | **Ciudad** | Población, superficie, renta por distritos, paro, turismo | INE Padrón + INE Renta + SEPE + EOH (vía ODM) | ✅ ambos grupos |
| 2 | **Gestión Económico-Financiera** | Rigor presupuestario, comparativa CONPREL, explorador, deuda, plan de ajuste | ETL Jerez + CONPREL + Cuenta General + Hacienda | ✅ ambos grupos |
| 3 | **Recursos Humanos** | RPT: plantilla, estructura, vacantes, organigrama | PDFs transparencia.jerez.es (pdfplumber) | ⚠️ solo si otros municipios tienen RPT accesible |
| 4 | **Calidad de Servicios** | Cartas de Servicio, compromisos, cumplimiento, KPI editor | ChoS (repo) | ⚠️ solo si otros municipios tienen ChoS |
| 5 | **Planes, Convenios y Proyectos** | Planes vigentes, convenios firmados, proyectos activos | ❓ fuente pendiente confirmar | ❓ |
| 6 | **Subvenciones** | Subvenciones recibidas y concedidas | BDNS (API pública infosubvenciones.es) | ✅ BDNS nacional |
| 7 | **Contratación Pública** | Licitaciones activas, contratos adjudicados | PLACE/PCSP (API pública) | ✅ PLACE nacional |

---

## Mapeo: Portal Transparencia → ODM Resource → KPIs → Dashboard

URL raíz del portal: `https://transparencia.jerez.es/infopublica/economica`

| Sección portal | URL primer nivel | Ficheros disponibles | ODM Resource (resource_code) | KPIs resultantes | Sección Dashboard |
|---|---|---|---|---|---|
| Ejecución presupuestaria | `/presupuesto/{year}` | XLSX/XLS gastos + ingresos (snapshots mensuales) | `jerez_ejecucion_gastos` + `jerez_ejecucion_ingresos` ✅ | Rigor presupuestario, ejecución por capítulo, modificaciones | Gestión Económico-Financiera |
| Cuenta General Ayto | `/cuentageneral/{year}` | Remite a rendiciondecuentas.es | Scraper CG (`services/cg_ayto_scraper.py`) | 44 KPIs sostenibilidad (CREPA, RT, Ind. Fin.) | Gestión Económico-Financiera |
| Ejecución gastos | `/presupuesto/{year}` | XLSX/XLS snapshots mensuales | `jerez_ejecucion_gastos` ✅ creado | Ejecución por capítulo/programa/económica, obligaciones reconocidas | Gestión Económico-Financiera |
| Ejecución ingresos | `/presupuesto/{year}` | XLSX/XLS snapshots mensuales | `jerez_ejecucion_ingresos` ✅ creado | Derechos reconocidos, recaudación neta por fuente | Gestión Económico-Financiera |
| PMP mensual | `/deuda/{year}` → `pmp/` | XLSX por entidad (Ayto + empresas) | `jerez_pmp_mensual` ✅ creado | PMP por entidad y mes, meses en incumplimiento, ratio pagos fuera de plazo | Gestión Económico-Financiera |
| Morosidad trimestral | `/deuda/{year}` → `morosidad/` | XLSX 2021 / PDF 2022+ (Ley 15/2010) | `jerez_morosidad_trimestral` ✅ creado (2021); Sprint 2 PDF 2022+ | Pagos fuera de plazo (importe y nº), facturas pendientes, intereses de demora | Gestión Económico-Financiera |
| Deuda financiera | `/deuda/{year}` → `deuda/` | XLSX 2024 / PDF resto | `jerez_deuda_financiera` ✅ creado (2024); Sprint 2 PDF resto | Deuda viva por acreedor (ICO, banca privada, etc.), deuda per cápita | Gestión Económico-Financiera |
| Coste efectivo servicios | `/otrainfo` → `costeservicios/` | XLSX 2014–2021 / PDF 2022+ | `jerez_cesel` ✅ creado (2014-2021); Sprint 2 PDF 2022+ | Coste por servicio y usuario, variación interanual | Calidad de Servicios |
| RPT (plantilla) | `/personal/rpt/` | XLSX RPT por ejercicio | ETL ad-hoc (`tasks/rpt_tasks.py`) ⏳ pendiente | Masa salarial, estructura por grupo, vacantes, coste/habitante | Recursos Humanos |
| Subvenciones concedidas | externo: `infosubvenciones.es` | API REST BDNS | `bdns_subvenciones` ⏳ pendiente | % concurrencia competitiva, tiempo resolución, reintegros | Subvenciones |
| Contratación pública | externo: `contrataciondelestado.es` | API REST PLACE | `place_contratos` ⏳ pendiente | % contratos menores, ahorro licitación, nº licitadores, concentración | Contratación Pública |
| Datos socioeconómicos | externo: INE / SEPE | APIs públicas | Via ODM webhook (Capa 3) | Población padrón, renta per cápita, tasa paro, pernoctaciones | Ciudad |
| Comparativa municipal | externo: Hacienda CONPREL | XLSX por año | ETL nativo (`tasks/conprel_tasks.py`) | Presupuesto per cápita, capítulos comparados, grupos de pares | Gestión Económico-Financiera |

### KPIs por grupo de dashboard

| Grupo KPI | KPIs | Semáforo / umbral legal |
|---|---|---|
| **Liquidez y Pagos** | PMP mensual Ayto, PMP mensual grupo, meses incumplimiento, ratio pagos fuera plazo | PMP > 30d → amarillo; > 60d → rojo (Ley 15/2010 art.5) |
| **Deuda** | Deuda viva, deuda/ingresos corrientes, deuda per cápita, variación YoY | Deuda/ingresos > 75% → amarillo; > 110% → rojo (LOEPSF) |
| **Ejecución presupuestaria** | % ejecución gastos (caps I–IX), % ejecución ingresos, desviaciones por modificación | Ejecución < 70% → amarillo; < 50% → rojo |
| **Sostenibilidad financiera** | Resultado presupuestario ajustado, remanente tesorería gastos generales, ahorro neto, regla de gasto | RTGG < 0 → rojo (LOEPSF art.3) |
| **Coste de servicios** | Coste por usuario por servicio CESEL, variación interanual, cobertura poblacional | Comparativo: referencia estatal CESEL |
| **Recursos Humanos** | Masa salarial / presupuesto, coste por habitante, ratio vacantes, tasa temporalidad | Masa salarial > 35% presupuesto → alerta |
| **Contratación** | % contratos menores, ahorro medio en licitación, tiempo adjudicación, concentración adjudicatarios | % contratos menores > 20% → revisar (fraccionamiento) |
| **Subvenciones** | % concurrencia competitiva vs directa, tiempo resolución, % justificadas correctamente, reintegros | % directas > 50% → revisar |

---

## Grupos de comparación

### Grupo A — Población (150k–250k hab.)
Municipios españoles con población entre 150.000 y 250.000 habitantes.
Ejemplos: Valladolid, Alicante, Vigo, L'Hospitalet, A Coruña, Vitoria, Gijón, Granada, Elche, Oviedo, Badalona, Cartagena, Terrassa, Sabadell...

**Slug BD:** `nacional-150k-250k` (todos), `andalucia-150k-250k` (solo Andalucía)

### Grupo B — Superficie (término municipal Jerez ±15%)
Municipios con superficie entre ~1.010 km² y ~1.366 km² (Jerez ≈ 1.188 km²).
Nota: Jerez es uno de los municipios más extensos de España — este grupo incluirá
municipios de distinto tamaño pero con similar extensión territorial.

**Slug BD:** `nacional-superficie-jerez`

**Datos necesarios:** `superficie_km2` en tabla `municipalities` (INE Nomenclator).

---

## Modelo de datos completo

```
── Capa 1: Presupuesto Jerez ──────────────────────────────────────────
fiscal_years              ← ejercicios 2020-2026
budget_snapshots          ← un snapshot por XLSX (phase: expense / revenue)
budget_lines              ← líneas presupuestarias
economic/functional/organic_classification
rigor_metrics             ← IPP, ITP, ITR, score global por ejercicio
budget_modifications

── Capa 2: Nacional (CONPREL + INE) ──────────────────────────────────
municipalities            ← catálogo INE (+ superficie_km2 pendiente añadir)
municipal_budgets         ← liquidaciones CONPREL totales
municipal_budget_chapters ← desglose por capítulo
municipal_budget_programs ← desglose por programa
municipal_population      ← población CONPREL (€/hab en CONPREL)
peer_groups               ← grupos de pares (criteria JSONB)
peer_group_members        ← municipios de cada grupo

── Capa 3: Socioeconómico (ODM) ──────────────────────────────────────
ine_padron_municipal      ← padrón INE todos municipios (webhook ODM)
ine_renta_municipal       ← Atlas distribución renta INE (webhook ODM)
ine_eoh_municipal         ← Encuesta Ocupación Hotelera INE (webhook ODM)
sepe_paro_municipal       ← paro registrado SEPE (webhook ODM)

── Capa 4: Sostenibilidad ────────────────────────────────────────────
cuenta_general_kpis       ← KPIs Cuenta General (scraper rendiciondecuentas.es)
                             + deuda viva Hacienda (webhook ODM)

── Capa 5: RPT ───────────────────────────────────────────────────────
rpt_puestos               ← plantilla (ETL PDFs transparencia.jerez.es)

── Capa 6: Subvenciones ──────────────────────────────────────────────
bdns_subvenciones         ← subvenciones BDNS (ETL API infosubvenciones.es)

── Capa 7: Contratación ──────────────────────────────────────────────
place_contratos           ← contratos PLACE/PCSP (ETL API contrataciondelestado.es)
```

---

## Historial de sprints

| Sprint | Commit | Contenido |
|--------|--------|-----------|
| S01 | `f6d1c2e` | Fundamentos: modelos ORM, FastAPI, docker-compose, Alembic |
| S02a | `cff2b22` | Panel admin Jinja2+HTMX — modificaciones presupuestarias |
| S02b | `c276cca` | ETL completo: scraper, parser XLSX, loader, Celery, métricas IPP/ITP/ITR |
| S03 | `a242efe` | GraphQL (Strawberry) + migración Alembic automatizada |
| S04 | `73bc074` | Modelo BD nacional: INE municipios, CONPREL, peer groups |
| S05 | `3927501` | ETL CONPREL: 8.000 municipios × 15 años desde MDB Hacienda |
| S06 | `290ef9f` | Capa OLAP babbage: cubos OLAP `/api/3/cubes/` |
| S07 | `d62bb72` | Dashboard Dash: `/rigor`, `/explorador`, `/comparativa` |
| S08 | `e2b485f` | Producción: Makefile, health checks, CI/CD |
| S09 | `c2791f3`–`236a6d4` | Estabilización: arranque stack, fixes ETL CONPREL + INE |
| S10 | `2387bec` | ODM integration + Cuenta General scraper (44 KPIs × 2016-2022) |
| S10b | `b62ae9e` | HANDOFF actualizado con roadmap |
| S11a | pendiente commit | Renombrado CityDashboard + city params + OSM module + superficie_km2 |

---

## Roadmap — sprints pendientes

### S11 — Renombrado + parametrización ciudad + OSM ✅ (parcial)
- ✅ Renombrar proyecto a CityDashboard (docker-compose, .env, README)
- ✅ BD renombrada: `citydashboard_db`; contenedores: `citydashboard_*`
- ✅ `app/config.py`: parámetros `CITY_*` configurables vía .env (cualquier ciudad española)
- ✅ `superficie_km2` + `osm_relation_id` + `lat/lon` en `municipalities`
- ✅ `services/osm.py`: módulo OSM con OverpassClient, Nominatim, helpers
- ✅ Migración `0005_s11_geo_superficie.py`
- ✅ `services/peer_groups.py`: soporte criterio `surface_min/surface_max`; `ensure_city_in_all_groups`
- ✅ `tasks/cuenta_general_tasks.py`: entidad de scraping desde `settings` (sin hardcoding)
- ⏳ `models/rpt.py` + migración 0006 (pospuesto a S13)
- ⏳ Seed `superficie_km2` desde INE Nomenclator (pospuesto)
- ⏳ Peer groups nuevos en BD (pospuesto)

### S12 — Vue 3 frontend: scaffolding + módulo Gestión Económico-Financiera ← EN CURSO
- Scaffolding: Vite + Vue 3 + Vue Router + graphql-request + ECharts
- Sidebar con las 7 secciones + selector de grupo de comparación (global)
- Migrar 3 vistas Dash existentes → `views/`: Rigor, Comparativa, Explorador
- Nuevos resolvers GraphQL: `conprelComparativa`, `peerGroups`
- Retirar servicio `dashboard` de docker-compose + deprecar capa OLAP

### S13 — Secciones Sostenibilidad + Recursos Humanos
- Vista Sostenibilidad (cuenta_general_kpis + deuda + benchmark)
- Vista RPT (plantilla, estructura, KPIs RRHH)

### S14 — Sección Calidad de Servicios + KPI Editor
- Integración ChoS
- Editor de KPIs composables desde estadísticas disponibles

### S15 — Secciones Subvenciones + Contratación Pública
- ETL BDNS (API infosubvenciones.es)
- ETL PLACE (API contrataciondelestado.es)
- Vistas correspondientes con comparativa nacional

### S16 — Sección Planes, Convenios y Proyectos
- Pendiente definir fuente de datos

---

## Operaciones habituales

```bash
# Reconstruir peer groups (tras actualizar municipios o criterios)
docker compose exec worker celery -A tasks.celery_app call \
  tasks.conprel_tasks.rebuild_peer_groups

# Recargar Cuenta General histórico
docker compose exec worker celery -A tasks.celery_app call \
  tasks.cuenta_general_tasks.load_historical_cg

# Recargar CONPREL un año
docker compose exec worker celery -A tasks.celery_app call \
  tasks.conprel_tasks.ingest_conprel_year --kwargs '{"year": 2023}'

# Reseed ODM
docker compose -f /opt/docker/apps/opendatamanager/docker-compose.yml \
  exec odmgr_app python seed_data.py

# BD
docker compose exec db psql -U jerezbudget -d jerezbudget
```

---

## TODO — Renombrado completo a CityDashboard

El proyecto ya usa `CityDashboard` en código y compose, pero la carpeta raíz y el repo GitHub aún se llaman `JerezBudgetAPI`. Para completar el renombrado:

### Pasos en orden

```bash
# 1. Renombrar carpeta en disco
mv /opt/docker/apps/JerezBudgetAPI /opt/docker/apps/CityDashboard

# 2. Redirigir memoria de Claude Code (contexto acumulado)
mv ~/.claude/projects/-opt-docker-apps-JerezBudgetAPI \
   ~/.claude/projects/-opt-docker-apps-CityDashboard

# 3. Actualizar paths hardcodeados en .claude/settings.json
#    (permisos de herramientas que usan el path absoluto)

# 4. Recrear contenedores desde la nueva ruta
cd /opt/docker/apps/CityDashboard
docker compose up -d --force-recreate
```

### Ficheros que requieren edición manual

| Fichero | Qué cambiar |
|---------|-------------|
| `.github/workflows/deploy.yml` | `jerezbudget-deploy.bundle` → `citydashboard-deploy.bundle`; rutas `~/jerezbudget-*` → `~/citydashboard-*` |
| `.github/workflows/ci.yml` | `POSTGRES_DB: jerezbudget_test`, `POSTGRES_USER: jerezbudget`, `DATABASE_URL` con `jerezbudget` → `citydashboard` |
| `Makefile` | `db-shell` usa `${DB_USER:-jerezbudget}` → `${DB_USER:-citydashboard}` |
| `tasks/cg_ayto_tasks.py` | Docstrings con `docker exec jerezbudget_worker` → `citydashboard_worker` |
| `dashboard/app.py` | Título y links GitHub |
| `README.md` | Título, badges, URLs |

### Ficheros ya actualizados ✅
`pyproject.toml` · `app/main.py` · `app/config.py` · `docker-compose.yml` · `docker-compose.prod.yml` · `HANDOFF.md` · `.env` · `tasks/celery_app.py`

### Impacto en BD
- DB renombrada: `jerezbudget` → `citydashboard_db` ✅ (ya hecho)
- Usuario `citydashboard` creado con permisos completos ✅
- Usuario `jerezbudget` (superuser) sigue existiendo para administración

---

## OpenDataManager — referencia rápida

### Conexión DB (desde el host)
```
Host: localhost  Port: 55432  User: odmgr_admin  Pass: Q7v!p2rX9eZs4@tL  DB: odmgr_db
docker exec odmgr_db psql -U odmgr_admin -d odmgr_db
```
Todas las tablas están en el schema `opendata` (ej: `opendata.resource`, `opendata.resource_param`).

### IDs fijos relevantes

| Entidad | ID |
|--------|---|
| Fetcher FILE_SERIES | `d134a881-bce2-49f8-b30f-94920fb87812` |
| Fetcher PDF_TABLE | `d4000001-0000-0000-0000-000000000001` |
| Publisher Ayto. Jerez | `88416e7d-40c7-48e0-8de3-4396124c44d8` |
| Resource Hacienda PMP | `5d8edffc-eb68-4f09-b5f7-4d758ec7305f` |
| Resource Jerez PMP Mensual | `a1b2c3d4-0001-0001-0001-000000000001` |
| Resource Jerez Ejecución Gastos | `a1b2c3d4-0002-0001-0001-000000000001` |
| Resource Jerez Ejecución Ingresos | `a1b2c3d4-0003-0001-0001-000000000001` |
| Resource Jerez CESEL | `a1b2c3d4-0004-0001-0001-000000000001` |
| Resource Jerez Deuda Financiera | `a1b2c3d4-0005-0001-0001-000000000001` |
| Resource Jerez Morosidad Trimestral | `a1b2c3d4-0006-0001-0001-000000000001` |

### Crear recursos ODM vía SQL
Los recursos se crean directamente en BD — la app los lee dinámicamente sin necesidad de reinicio.

```sql
INSERT INTO opendata.resource (id, name, publisher, fetcher_id, publisher_id, active, description, target_table, enable_load, load_mode, created_at)
VALUES (...);
INSERT INTO opendata.resource_param (id, resource_id, key, value, is_external) VALUES (...);
```

### Recurso: Jerez PMP Mensual (transparencia.jerez.es)

El portal cambia el nombre de los ficheros cada año (`2021_01Enero_CodEntidad.xlsx` vs `Informe_PMP_2024_5.xlsx`). La solución es que el **recurso** descubra los enlaces del índice en lugar de adivinar URLs.

- **Modo**: `url_segments` con `discovery_url_template` — el recurso carga la página de índice anual y descarga todos los xlsx encontrados
- **discovery_url_template**: `https://transparencia.jerez.es/infopublica/economica/deuda/{year}`
- **year_from/to**: 2021–2026 · **granularity**: annual
- **Sheet**: `Detalle` · **skip_rows**: `12` (válido para 2021 y 2024+)
- **column_map**: `codigo_de_entidad=codigo_entidad,entidad=entidad,periodo_medio_de_pago_mensual=pmp_dias,_year=ejercicio`
  - ⚠️ `_normalize_col()` transforma las cabeceras XLSX antes de aplicar column_map — usar siempre los nombres normalizados (lowercase, sin tildes, espacios→`_`)
- **keep_columns**: `codigo_entidad,entidad,pmp_dias,ejercicio`
- **filter_nonempty**: `entidad,pmp_dias` — descarta automáticamente ficheros de morosidad/deuda que no tienen `pmp_dias`
- Produce ~590 registros (2021-2026): ~10 entidades/mes × 12 meses (Ayuntamiento + OPAs + fundaciones + empresas)

### `url_segments` + `discovery_url_template` — patrón para portales con URLs cambiantes
```json
[{
  "discovery_url_template": "https://portal/{year}/indice",
  "link_base_url": "https://portal",
  "year_from": 2021, "year_to": 2026, "granularity": "annual",
  "sheet": "Detalle", "skip_rows": 12,
  "column_map": "...", "keep_columns": "...", "filter_nonempty": "..."
}]
```
Sin `link_pattern` → descarga todos los xlsx de la página índice. Varios tramos permiten distintos `skip_rows`/`sheet` por rango de años.

---

## Decisiones técnicas relevantes

| Problema | Solución |
|----------|----------|
| Phase collision snapshots | `phase="executed_expense"/"executed_revenue"` en constraint |
| Event loop en Celery | Cada tarea llama `engine.dispose()` + `asyncio.run()` propio |
| Double JSESSIONID en scraper CG | `requests` en lugar de `httpx` (gestiona cookies por path) |
| RTGG no calculable desde CONPREL | Scraped de rendiciondecuentas.es (portal Tribunal de Cuentas) |
| GraphQL / Pydantic incompatibilidad | Strawberry 0.249 + pydantic 2.11: try/except en startup |
| RPT en PDF | pdfplumber para extraer tablas de los 6 PDFs por tenencia |
| Peer group superficie | superficie_km2 en municipalities desde INE Nomenclator |

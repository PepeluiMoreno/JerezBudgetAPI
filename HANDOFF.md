# JerezBudgetAPI — Handoff

## Qué es esto

API + Dashboard para analizar el **rigor presupuestario** del Ayuntamiento de Jerez de la Frontera y la **situación socioeconómica** de la ciudad, comparándola con municipios de tamaño similar y con medias provinciales, autonómicas y nacionales.

El proyecto responde a dos preguntas:
1. **¿Gestiona bien el ayuntamiento?** — Precisión presupuestaria, deuda, pago a proveedores.
2. **¿Cómo está la ciudad?** — Paro, renta, demografía, turismo, benchmarking.

---

## Stack

```
FastAPI (8015)  ←→  PostgreSQL 16  ←→  MinIO (9000)
     ↑                   ↑
Celery workers       Alembic
     ↑
  Redis (6379)
     ↑
Dash dashboard (8050)
```

**Celery queues**: `etl` (ingestión XLSX), `metrics` (cálculo rigor)
**MinIO**: caché de ficheros XLSX descargados (idempotencia HTTP)

---

## Fuentes de datos actuales

| Fuente | Qué contiene | Estado |
|---|---|---|
| transparencia.jerez.es | Ejecución presupuestaria anual XLSX (gastos + ingresos), 2020–2026 | ✅ ETL activo |
| CONPREL (Hacienda) | Liquidaciones de 8.000+ municipios, 2010–2024, formato MDB | ✅ ETL activo |
| INE Padrón | Población municipal anual | 🔄 Vía ODM (pendiente) |

---

## Modelo de datos (PostgreSQL, schema `public`)

```
fiscal_years          ← ejercicio presupuestario (2020-2026)
budget_snapshots      ← un snapshot por fichero XLSX (phase: executed_expense / executed_revenue)
budget_lines          ← líneas presupuestarias (clasificación eco + func + org)
economic_classification
functional_classification
organic_classification
rigor_metrics         ← métricas calculadas por ejercicio (IPP, ITP, ITR, score global)
municipal_budgets     ← presupuestos de municipios nacionales (CONPREL)
municipalities        ← catálogo de municipios con código INE
peer_groups           ← grupos de pares para benchmarking
```

---

## KPIs implementados

### Rigor presupuestario (disponibles en /api/3/cubes/jerez-rigor)
| Índice | Fórmula |
|---|---|
| **IPP** — Precisión | Obligaciones / Créditos iniciales |
| **ITP** — Puntualidad | 0 si presupuesto prorrogado; 1 − (días_retraso / 365) si aprobado |
| **ITR** — Transparencia | Documentos publicados / documentos esperados |
| **Score Global** | Promedio ponderado IPP·0.4 + ITP·0.3 + ITR·0.3 |
| Tasa ejecución gasto | Obligaciones reconocidas / Créditos definitivos |
| Tasa ejecución ingreso | Derechos reconocidos / Previsiones definitivas |
| Tasa modificación | (Créditos definitivos − iniciales) / iniciales |

### KPIs pendientes de datos adicionales
| KPI | Fuente necesaria |
|---|---|
| Gasto per cápita por capítulo | INE Padrón (ODM) |
| Presión fiscal municipal | INE Padrón + cap. 1-3 ingresos |
| PMP (Periodo Medio de Pago) | Hacienda-EL (ODM) |
| Paro municipal | SEPE (ODM) |
| Renta media per cápita | INE Atlas Renta (ODM) |
| Deuda viva / RTGG / ahorro neto | Cuenta General XBRL (ODM) |
| Pernoctaciones hoteleras | INE EOH (ODM) |

---

## Integración con OpenDataManager (ODM)

ODM (`http://odmgr_app:8000`) actúa como hub de datos abiertos. Cuando publica un nuevo dataset, notifica a JerezBudgetAPI vía webhook HMAC-signed en `/webhooks/odmgr`.

**Recursos configurados en ODM que alimentan este proyecto:**
- `INE - Padrón Municipal` → tabla `ine_padron_municipal`
- `INE - Atlas Distribución Renta` → tabla `ine_renta_municipal`
- `INE - Encuesta Ocupación Hotelera` → tabla `ine_eoh_municipal`
- `SEPE - Paro Registrado por Municipio` → tabla `sepe_paro_municipal`
- `Hacienda - PMP Entidades Locales` → tabla `hacienda_pmp_el`
- `Cuenta General XBRL` → tabla `cuenta_general_el`

**Pendiente implementar en JerezBudgetAPI:**
- Endpoint `POST /webhooks/odmgr` — recibe notificación ODM, descarga JSONL, carga en BD
- Modelos SQLAlchemy para las tablas nuevas
- Migración Alembic
- Cálculo de KPIs per cápita y sostenibilidad

---

## Dashboard (Dash, puerto 8050)

### Vistas actuales
| Ruta | Contenido |
|---|---|
| `/rigor` | Score global, IPP/ITP/ITR, histórico 2020-2026, ejecución por capítulo |
| `/explorador` | Explorador libre de datos OLAP (cube jerez-detail) |
| `/comparativa` | Benchmarking Jerez vs municipios similares (CONPREL) |

### Vistas planificadas
| Ruta | Contenido |
|---|---|
| `/socioeconomico` | Dashboard ciudad: paro, renta, demografía, turismo vs benchmarks |
| `/sostenibilidad` | Deuda, RTGG, PMP, ahorro neto — evolución y comparativa |
| `/cuenta-general` | Balance, liquidación, tesorería desglosados año a año |

---

## Grupo de comparación

Jerez de la Frontera (213.000 hab.) se compara con:
- **Municipios 180k–250k hab.** de España (≈ 15 ciudades): Valladolid, Alicante, Vigo, L'Hospitalet, A Coruña, Vitoria, Gijón, Granada, Elche, Oviedo...
- **Media Andalucía** (ponderada por población)
- **Media nacional** (ponderada por población)

El grupo de pares se actualiza anualmente con el Padrón Municipal del INE.

---

## Operaciones habituales

```bash
# Forzar recarga del histórico (tras reset de BD o cambio de parser)
docker compose exec api python -c "
from tasks.etl_tasks import load_historical
load_historical.apply_async(queue='etl')
"

# Ver estado del worker
docker compose exec worker celery -A tasks.celery_app inspect active

# Ejecutar seed ODM (tras cambios en seed_data.py)
docker compose exec odmgr_app python seed_data.py

# Acceder a la BD
docker compose exec db psql -U jerezbudget -d jerezbudget
```

---

## Arquitectura de decisiones relevantes

- **Phase collision fix**: Los snapshots de gastos e ingresos usan `phase="executed_expense"` / `"executed_revenue"` para evitar colisión en la constraint `uq_snapshot_year_date_phase`.
- **Event loop fix en Celery**: Cada tarea crea su propio `AsyncEngine` dentro de `asyncio.run()` para evitar "Future attached to a different loop". No se reutiliza el engine de `app/db.py` en workers.
- **MinIO ≠ idempotencia BD**: MinIO cachea ficheros descargados (evita HTTP redundante). La idempotencia de BD se controla por SHA256 en `BudgetSnapshot.source_sha256`. Son mecanismos distintos.
- **GraphQL opcional**: `strawberry 0.249` es incompatible con `pydantic 2.11+`. La API arranca aunque GraphQL falle (try/except en `app/main.py`).

# JerezBudget API

> API GraphQL de **rigor presupuestario** para el Ayuntamiento de Jerez de la Frontera.  
> Ingiere los datos de [transparencia.jerez.es](https://transparencia.jerez.es) y los expone
> en formato compatible con [OpenBudgets.eu](https://openbudgets.eu).

## Stack

| Capa | Tecnología |
|------|-----------|
| API | FastAPI 0.115 + Strawberry GraphQL |
| Base de datos | PostgreSQL 16 + SQLAlchemy 2.0 async |
| ETL | Celery 5 + Redis + httpx + openpyxl |
| Almacenamiento | MinIO (S3-compatible) |
| Infraestructura | Docker Compose + Traefik v3 |

## Arranque rápido

```bash
git clone git@github.com:PepeluiMoreno/JerezBudgetAPI.git
cd JerezBudgetAPI
cp .env.example .env        # editar passwords
docker compose up -d db redis minio
docker compose run --rm api alembic upgrade head
docker compose up -d api worker beat
# Abrir http://localhost:8000/graphql
```

## Queries GraphQL de ejemplo

```graphql
query {
  rigorMetrics(fiscalYear: 2025) {
    globalRigorScore
    expenseExecutionRate
    approvalDelayDays
    byChapter
  }
}

query {
  deviationAnalysis(fiscalYear: 2025, by: "chapter") {
    code name deviationPct modificationPct executionRate
  }
}

query {
  rigorTrend(years: [2020, 2021, 2022, 2023, 2024, 2025]) {
    fiscalYear globalRigorScore expenseExecutionRate approvalDelayDays
  }
}
```

## Índices de rigor

| Índice | Fórmula | Peso |
|--------|---------|------|
| IPP Precisión | `100 - \|1 - tasa_ejecución\| × 100` | 50% |
| ITP Puntualidad | `max(0, 100 - días_retraso × 0.5)` | 30% |
| ITR Transparencia | `max(0, 100 - días_publicación × 1.0)` | 20% |
| **Score Global** | `IPP×0.5 + ITP×0.3 + ITR×0.2` | — |

> ⚠️ **2026** es prórroga del presupuesto 2025 → ITP = 0 automáticamente.

## Roadmap

- [x] **S01** — Fundamentos: modelos ORM, GraphQL mínimo, Docker Compose
- [ ] **S02** — ETL: scraper, parser XLSX/PDF, Celery, histórico 2020-2025
- [ ] **S03** — GraphQL completo: filtros avanzados, modificaciones, trend
- [ ] **S04** — Métricas de rigor: IPP, ITP, ITR, score global
- [ ] **S05** — OpenBudgets export: endpoint /fdp/{year} (Fiscal Data Package)
- [ ] **S06** — Producción: Traefik TLS, Prometheus, CI/CD

## Licencia

[AGPL-3.0](LICENSE) — © 2026 [intramurosjerez.org](https://intramurosjerez.org)

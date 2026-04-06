# ─────────────────────────────────────────────────────────────────────────────
# JerezBudget API — Makefile
# Comandos de operación para desarrollo y producción.
#
# Uso: make <target>
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help dev prod up down logs ps shell db-shell migrate seed \
        load-historical test lint format clean push-bundle

COMPOSE      = docker compose
COMPOSE_PROD = docker compose -f docker-compose.yml -f docker-compose.prod.yml
APP_SERVICE  = api
WORKER       = worker

# ── Ayuda ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  JerezBudget API — comandos disponibles"
	@echo ""
	@echo "  Desarrollo:"
	@echo "    make dev          Levanta todos los servicios en modo desarrollo"
	@echo "    make up           docker compose up -d"
	@echo "    make down         docker compose down"
	@echo "    make logs         Logs en tiempo real de todos los servicios"
	@echo "    make ps           Estado de los contenedores"
	@echo "    make shell        Shell en el contenedor API"
	@echo "    make db-shell     psql en PostgreSQL"
	@echo ""
	@echo "  Base de datos:"
	@echo "    make migrate      Aplica migraciones Alembic pendientes"
	@echo "    make migrate-down Revierte la última migración"
	@echo "    make seed         Carga catálogo de municipios INE"
	@echo ""
	@echo "  Datos:"
	@echo "    make load-jerez   Descubre y carga XLSX de transparencia.jerez.es"
	@echo "    make load-ine-pop Carga padrón municipal INE (serie histórica)"
	@echo "    make load-conprel Carga histórico CONPREL 2010-2024"
	@echo "    make rebuild-peer Recalcula grupos de pares"
	@echo "    make refresh-view Refresca vista materializada mv_comparison_jerez"
	@echo ""
	@echo "  Calidad:"
	@echo "    make test         Ejecuta suite de tests pytest"
	@echo "    make lint         Ruff linter"
	@echo "    make format       Ruff formatter"
	@echo ""
	@echo "  Producción:"
	@echo "    make prod         Levanta con docker-compose.prod.yml (Traefik+TLS)"
	@echo "    make prod-down    Baja producción"
	@echo "    make prod-logs    Logs de producción"
	@echo ""

# ── Desarrollo ────────────────────────────────────────────────────────────────
dev: up migrate
	@echo "✅  Stack levantado:"
	@echo "    GraphQL:    http://localhost:8000/graphql"
	@echo "    Admin:      http://localhost:8000/admin"
	@echo "    OLAP API:   http://localhost:8000/api/3/cubes/"
	@echo "    Dashboard:  http://localhost:8050"
	@echo "    Flower:     http://localhost:5555"
	@echo "    MinIO:      http://localhost:9001"

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec $(APP_SERVICE) bash

db-shell:
	$(COMPOSE) exec db psql -U $${DB_USER:-jerezbudget} $${DB_NAME:-jerezbudget}

# ── Base de datos ─────────────────────────────────────────────────────────────
migrate:
	$(COMPOSE) run --rm $(APP_SERVICE) alembic upgrade head

migrate-down:
	$(COMPOSE) run --rm $(APP_SERVICE) alembic downgrade -1

migrate-show:
	$(COMPOSE) run --rm $(APP_SERVICE) alembic current
	$(COMPOSE) run --rm $(APP_SERVICE) alembic history --verbose

# ── Datos ─────────────────────────────────────────────────────────────────────
seed:
	$(COMPOSE) run --rm $(APP_SERVICE) python scripts/seed_municipalities.py

load-jerez:
	$(COMPOSE) exec $(WORKER) celery -A tasks.celery_app call \
		tasks.etl_tasks.discover_and_ingest \
		--kwargs '{"years": null}'

load-ine-pop:
	$(COMPOSE) exec $(WORKER) celery -A tasks.celery_app call \
		tasks.conprel_tasks.seed_ine_population

load-conprel:
	$(COMPOSE) exec $(WORKER) bash scripts/load_historical_conprel.sh

rebuild-peer:
	$(COMPOSE) exec $(WORKER) celery -A tasks.celery_app call \
		tasks.conprel_tasks.rebuild_peer_groups

refresh-view:
	$(COMPOSE) exec db psql -U $${DB_USER:-jerezbudget} $${DB_NAME:-jerezbudget} \
		-c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_comparison_jerez;"

# ── Calidad de código ─────────────────────────────────────────────────────────
test:
	$(COMPOSE) run --rm $(APP_SERVICE) \
		pytest tests/ -v --tb=short --color=yes

test-fast:
	$(COMPOSE) run --rm $(APP_SERVICE) \
		pytest tests/ -v --tb=short -x --color=yes

lint:
	$(COMPOSE) run --rm $(APP_SERVICE) ruff check .

format:
	$(COMPOSE) run --rm $(APP_SERVICE) ruff format .

typecheck:
	$(COMPOSE) run --rm $(APP_SERVICE) mypy app/ models/ graphql/ api/ --ignore-missing-imports

# ── Producción ────────────────────────────────────────────────────────────────
prod:
	@test -f .env || (echo "ERROR: .env no encontrado. cp .env.example .env" && exit 1)
	$(COMPOSE_PROD) up -d
	@echo "✅  Producción levantada"
	@echo "    API:        https://budget.$${DOMAIN}"
	@echo "    Dashboard:  https://presupuestos.$${DOMAIN}"
	@echo "    Flower:     https://flower.$${DOMAIN}"

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f --tail=100

prod-migrate:
	$(COMPOSE_PROD) run --rm $(APP_SERVICE) alembic upgrade head

# ── Git bundle para transferencia al VPS ─────────────────────────────────────
push-bundle:
	@git bundle create jerezbudget-latest.bundle --all
	@echo "Bundle creado: jerezbudget-latest.bundle"
	@echo "Transferir con: scp jerezbudget-latest.bundle jose@optiplex-790:~/bundles/"

# ── Limpieza ──────────────────────────────────────────────────────────────────
clean:
	$(COMPOSE) down -v --remove-orphans
	@echo "⚠️  Volúmenes eliminados (datos borrados)"

clean-cache:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cache limpiada"

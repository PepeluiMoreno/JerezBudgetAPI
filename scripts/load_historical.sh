#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/load_historical.sh
# Dispara la carga del histórico completo (2020-2026) via Celery.
# Ejecutar una sola vez tras el primer arranque con la BD vacía.
#
# Uso:
#   docker compose exec worker bash scripts/load_historical.sh
#   # o directamente:
#   bash scripts/load_historical.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "🚀  Disparando carga histórica presupuestaria 2020-2026..."
echo "    (los ficheros se descargan desde transparencia.jerez.es)"
echo ""

celery -A tasks.celery_app call \
  tasks.etl_tasks.load_historical \
  --args='[]' \
  --kwargs='{"years": [2020, 2021, 2022, 2023, 2024, 2025, 2026]}'

echo ""
echo "✅  Tarea encolada. Monitoriza el progreso en:"
echo "    http://localhost:5555  (Flower)"
echo ""
echo "📋  Para ver logs del worker en tiempo real:"
echo "    docker compose logs -f worker"

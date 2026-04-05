#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/load_historical_conprel.sh
#
# Dispara la carga histórica completa del CONPREL (2010-2024).
# Ejecutar después de:
#   1. alembic upgrade head
#   2. python scripts/seed_municipalities.py
#   3. celery task seed_ine_population (o esperar a que lo haga el beat)
#
# Uso:
#   docker compose exec worker bash scripts/load_historical_conprel.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "📥  Iniciando carga histórica CONPREL 2010-2024..."
echo "    Los ficheros MDB se descargan desde el Ministerio de Hacienda."
echo "    Cada año se procesa con 60s de delay para no saturar el servidor."
echo ""

celery -A tasks.celery_app call \
  tasks.conprel_tasks.load_historical_conprel \
  --kwargs '{"years": [2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024], "countdown_between": 60}'

echo ""
echo "✅  Tareas encoladas. Tiempo estimado: ~25 minutos para el histórico completo."
echo ""
echo "📊  Monitoriza en: http://localhost:5555 (Flower)"
echo "📋  Logs del worker: docker compose logs -f worker"
echo ""
echo "⚠️  Si algún año falla (URL no encontrada), descarga el MDB manualmente desde:"
echo "    https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"
echo "    y vuelve a encolar con:"
echo "    celery -A tasks.celery_app call tasks.conprel_tasks.ingest_conprel_year \\"
echo "      --kwargs '{\"year\": YYYY, \"mdb_local_path\": \"/ruta/al/fichero.mdb\"}'"

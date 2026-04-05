"""
Configuración de la aplicación Celery.
Se importa desde todos los módulos de tasks.
"""
from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "jerezbudget",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["tasks.etl_tasks", "tasks.conprel_tasks"],
)

celery_app.conf.update(
    # Serialización
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Madrid",
    enable_utc=True,

    # Reintentos
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,

    # Resultado
    result_expires=86400,   # 24h

    # Rutas de colas
    task_routes={
        # Capa 1 — JerezBudget
        "tasks.etl_tasks.discover_and_ingest":            {"queue": "etl"},
        "tasks.etl_tasks.ingest_file":                    {"queue": "etl"},
        "tasks.etl_tasks.compute_metrics":                {"queue": "metrics"},
        # Capa 2 — CONPREL + INE
        "tasks.conprel_tasks.seed_ine_population":        {"queue": "etl"},
        "tasks.conprel_tasks.ingest_conprel_year":        {"queue": "etl"},
        "tasks.conprel_tasks.rebuild_peer_groups":        {"queue": "etl"},
        "tasks.conprel_tasks.load_historical_conprel":    {"queue": "etl"},
    },

    # Scheduler periódico
    beat_schedule={
        # Capa 1: descubrir nuevos XLSX de Jerez cada día
        "daily-jerez-discovery": {
            "task": "tasks.etl_tasks.discover_and_ingest",
            "schedule": crontab(hour=7, minute=30),
            "kwargs": {"years": None},
        },
        # Capa 2: refrescar liquidación CONPREL del año anterior (enero)
        "annual-conprel-liquidation": {
            "task": "tasks.conprel_tasks.ingest_conprel_year",
            "schedule": crontab(month_of_year=1, day_of_month=20, hour=6, minute=0),
            "kwargs": {},   # year se calcula dinámicamente en la task
        },
        # Capa 2: refrescar padrón INE (julio — el INE publica en verano)
        "annual-ine-population": {
            "task": "tasks.conprel_tasks.seed_ine_population",
            "schedule": crontab(month_of_year=7, day_of_month=15, hour=5, minute=0),
            "kwargs": {},
        },
    },
)

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
    include=["tasks.etl_tasks"],
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
        "tasks.etl_tasks.discover_and_ingest": {"queue": "etl"},
        "tasks.etl_tasks.ingest_file":         {"queue": "etl"},
        "tasks.etl_tasks.compute_metrics":     {"queue": "metrics"},
    },

    # Scheduler periódico
    beat_schedule={
        "daily-discovery": {
            "task": "tasks.etl_tasks.discover_and_ingest",
            "schedule": crontab(hour=7, minute=30),
            "args": [],
            "kwargs": {"years": None},   # None = todos los años
        },
    },
)

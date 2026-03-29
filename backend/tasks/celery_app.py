from celery import Celery
from config import settings

celery_app = Celery(
    "agentshub",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks.execute_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={"tasks.execute_task.*": {"queue": "executions"}},
    # Результаты хранятся 24 часа
    result_expires=86400,
)

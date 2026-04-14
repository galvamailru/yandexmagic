from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery = Celery(
    "yandexmagic",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    imports=("app.tasks.agent_tasks",),
    beat_schedule={
        "agent-every-6-hours": {
            "task": "app.tasks.agent_tasks.run_agent_cycle",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)

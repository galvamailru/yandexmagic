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
        "domain-anomaly-watchdog": {
            "task": "app.tasks.agent_tasks.run_domain_cycle",
            "schedule": crontab(minute=0, hour="*/3"),
            "args": ("anomaly_watchdog",),
        },
        "domain-budget-guard": {
            "task": "app.tasks.agent_tasks.run_domain_cycle",
            "schedule": crontab(minute=30, hour="*/4"),
            "args": ("budget_guard",),
        },
        "domain-bid-optimization": {
            "task": "app.tasks.agent_tasks.run_domain_cycle",
            "schedule": crontab(minute=10, hour=2),
            "args": ("bid_optimization",),
        },
        "domain-keyword-hygiene": {
            "task": "app.tasks.agent_tasks.run_domain_cycle",
            "schedule": crontab(minute=40, hour=2),
            "args": ("keyword_hygiene",),
        },
        "domain-ad-rotation": {
            "task": "app.tasks.agent_tasks.run_domain_cycle",
            "schedule": crontab(minute=15, hour=4, day_of_week="1,3,5"),
            "args": ("ad_rotation",),
        },
        "domain-retargeting": {
            "task": "app.tasks.agent_tasks.run_domain_cycle",
            "schedule": crontab(minute=25, hour=5, day_of_week="0"),
            "args": ("retargeting_tuning",),
        },
        "agent-full-backward-compatible": {
            "task": "app.tasks.agent_tasks.run_agent_cycle",
            "schedule": crontab(minute=0, hour="*/12"),
        },
    },
)

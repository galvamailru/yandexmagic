import asyncio

from app.celery_app import celery
from app.database import SessionLocal
from app.models.public import Tenant
from app.services.agent_runner import run_for_tenant


@celery.task(name="app.tasks.agent_tasks.run_agent_cycle")
def run_agent_cycle() -> str:
    db = SessionLocal()
    try:
        tenants = db.query(Tenant).all()
    finally:
        db.close()
    n = 0
    for t in tenants:
        s = SessionLocal()
        try:
            asyncio.run(run_for_tenant(s, t))
            n += 1
        finally:
            s.close()
    return f"ok:{n}"

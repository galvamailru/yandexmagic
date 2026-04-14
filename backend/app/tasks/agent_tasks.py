import asyncio
import json
import time
import uuid

from sqlalchemy import text

from app.celery_app import celery
from app.database import SessionLocal
from app.models.public import Tenant
from app.services.request_context import set_correlation_id
from app.services.agent_runner import run_for_tenant


@celery.task(name="app.tasks.agent_tasks.run_agent_cycle")
def run_agent_cycle() -> str:
    run_id = str(uuid.uuid4())
    set_correlation_id(run_id)
    db = SessionLocal()
    started = int(time.time() * 1000)
    try:
        # distributed lock
        lock = db.execute(
            text(
                """
INSERT INTO job_locks(name, locked_until)
VALUES ('agent_cycle', NOW() + INTERVAL '25 minutes')
ON CONFLICT (name) DO UPDATE SET locked_until = EXCLUDED.locked_until
WHERE job_locks.locked_until < NOW()
RETURNING name
"""
            )
        ).fetchone()
        if not lock:
            return "skipped:locked"
        db.execute(
            text(
                """
INSERT INTO job_runs(id, name, status, started_at, details)
VALUES (:id, 'agent_cycle', 'running', NOW(), :d)
"""
            ),
            {"id": run_id, "d": json.dumps({"correlation_id": run_id})},
        )
        db.commit()
        tenants = db.query(Tenant).all()
    finally:
        db.close()
    n = 0
    errors = 0
    for t in tenants:
        s = SessionLocal()
        try:
            try:
                asyncio.run(run_for_tenant(s, t))
                n += 1
            except Exception:  # noqa: BLE001
                errors += 1
        finally:
            s.close()
    finish = int(time.time() * 1000)
    db2 = SessionLocal()
    try:
        db2.execute(
            text(
                """
UPDATE job_runs
SET status=:status, finished_at=NOW(), duration_ms=:dur, details=:d
WHERE id=:id
"""
            ),
            {
                "id": run_id,
                "status": "success" if errors == 0 else "partial_error",
                "dur": finish - started,
                "d": json.dumps({"processed_tenants": n, "errors": errors, "correlation_id": run_id}),
            },
        )
        db2.commit()
    finally:
        db2.close()
    return f"ok:{n}:err:{errors}"

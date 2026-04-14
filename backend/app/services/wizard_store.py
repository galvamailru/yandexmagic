import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def upsert_wizard(db: Session, tenant_id: UUID, step: int, payload: dict[str, Any]) -> UUID:
    wid = uuid.uuid4()
    db.execute(text("DELETE FROM wizard_sessions WHERE tenant_id = :tid"), {"tid": str(tenant_id)})
    db.execute(
        text(
            """
INSERT INTO wizard_sessions (id, tenant_id, step, payload, updated_at)
VALUES (:id, :tid, :step, :payload, NOW())
"""
        ),
        {"id": str(wid), "tid": str(tenant_id), "step": step, "payload": json.dumps(payload, ensure_ascii=False)},
    )
    db.commit()
    return wid


def get_wizard(db: Session, tenant_id: UUID) -> dict[str, Any] | None:
    row = db.execute(
        text("SELECT id, step, payload FROM wizard_sessions WHERE tenant_id = :tid ORDER BY updated_at DESC LIMIT 1"),
        {"tid": str(tenant_id)},
    ).fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "step": row[1], "payload": json.loads(row[2] or "{}")}

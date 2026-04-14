from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def _set_path(db: Session, schema: str) -> None:
    db.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


def upsert_campaign(
    db: Session,
    schema: str,
    yandex_campaign_id: int,
    name: str,
    state: str,
    mode: str = "monitoring",
) -> UUID:
    _set_path(db, schema)
    new_id = uuid.uuid4()
    row = db.execute(
        text(
            f'''
INSERT INTO "{schema}".campaigns (id, yandex_campaign_id, name, state, mode, created_at, updated_at)
VALUES (:id, :ycid, :name, :state, :mode, NOW(), NOW())
ON CONFLICT (yandex_campaign_id) DO UPDATE SET
  name = EXCLUDED.name,
  state = EXCLUDED.state,
  updated_at = NOW()
RETURNING id
'''
        ),
        {"id": str(new_id), "ycid": yandex_campaign_id, "name": name, "state": state, "mode": mode},
    ).fetchone()
    db.commit()
    return UUID(str(row[0])) if row else new_id


def list_campaigns(db: Session, schema: str) -> list[dict[str, Any]]:
    _set_path(db, schema)
    rows = db.execute(
        text(
            f'SELECT id, yandex_campaign_id, name, state, mode, created_at FROM "{schema}".campaigns ORDER BY name'
        )
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "yandex_campaign_id": int(r[1]),
            "name": r[2],
            "state": r[3],
            "mode": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


def update_campaign_mode(db: Session, schema: str, campaign_uuid: UUID, mode: str) -> bool:
    _set_path(db, schema)
    res = db.execute(
        text(f'UPDATE "{schema}".campaigns SET mode = :m, updated_at = NOW() WHERE id = :id'),
        {"m": mode, "id": str(campaign_uuid)},
    )
    db.commit()
    return res.rowcount > 0


def get_campaign_by_id(db: Session, schema: str, campaign_uuid: UUID) -> dict[str, Any] | None:
    _set_path(db, schema)
    r = db.execute(
        text(
            f'SELECT id, yandex_campaign_id, name, state, mode, created_at FROM "{schema}".campaigns WHERE id = :id'
        ),
        {"id": str(campaign_uuid)},
    ).fetchone()
    if not r:
        return None
    return {
        "id": str(r[0]),
        "yandex_campaign_id": int(r[1]),
        "name": r[2],
        "state": r[3],
        "mode": r[4],
        "created_at": r[5].isoformat() if r[5] else None,
    }


def insert_daily_stat(
    db: Session,
    schema: str,
    campaign_id: UUID,
    stat_date: date,
    cost_rub: Decimal,
    clicks: int,
    impressions: int,
    ctr: float,
    avg_cpc: Decimal | None,
) -> None:
    _set_path(db, schema)
    sid = uuid.uuid4()
    db.execute(
        text(
            f'''
INSERT INTO "{schema}".daily_stats (id, campaign_id, stat_date, cost_rub, clicks, impressions, ctr, avg_cpc_rub)
VALUES (:id, :cid, :d, :cost, :cl, :impr, :ctr, :cpc)
ON CONFLICT (campaign_id, stat_date) DO UPDATE SET
  cost_rub = EXCLUDED.cost_rub,
  clicks = EXCLUDED.clicks,
  impressions = EXCLUDED.impressions,
  ctr = EXCLUDED.ctr,
  avg_cpc_rub = EXCLUDED.avg_cpc_rub
'''
        ),
        {
            "id": str(sid),
            "cid": str(campaign_id),
            "d": stat_date,
            "cost": str(cost_rub),
            "cl": clicks,
            "impr": impressions,
            "ctr": ctr,
            "cpc": str(avg_cpc) if avg_cpc is not None else None,
        },
    )
    db.commit()


def dashboard_totals(db: Session, schema: str) -> tuple[int, Decimal, Decimal | None]:
    _set_path(db, schema)
    c = db.execute(text(f'SELECT COUNT(*) FROM "{schema}".campaigns')).scalar() or 0
    row = db.execute(
        text(
            f'''
SELECT COALESCE(SUM(cost_rub),0), COALESCE(SUM(clicks),0) FROM "{schema}".daily_stats ds
JOIN "{schema}".campaigns c ON c.id = ds.campaign_id
'''
        )
    ).fetchone()
    total_cost = Decimal(str(row[0] or 0))
    total_clicks = int(row[1] or 0)
    avg_cpc = (total_cost / Decimal(total_clicks)) if total_clicks else None
    return int(c), total_cost, avg_cpc


def spend_by_day(db: Session, schema: str, days: int = 14) -> list[dict[str, Any]]:
    _set_path(db, schema)
    rows = db.execute(
        text(
            f'''
SELECT stat_date::text, SUM(cost_rub) AS cost
FROM "{schema}".daily_stats
WHERE stat_date >= CURRENT_DATE - (:days)::integer
GROUP BY stat_date
ORDER BY stat_date
'''
        ),
        {"days": days},
    ).fetchall()
    return [{"date": r[0], "cost_rub": float(r[1])} for r in rows]


def recent_recommendations(db: Session, schema: str, limit: int = 20) -> list[dict[str, Any]]:
    _set_path(db, schema)
    rows = db.execute(
        text(
            f'''
SELECT id, campaign_id, kind, title, body, status, created_at
FROM "{schema}".recommendations
ORDER BY created_at DESC
LIMIT :lim
'''
        ),
        {"lim": limit},
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": str(r[0]),
                "campaign_id": str(r[1]) if r[1] else None,
                "kind": r[2],
                "title": r[3],
                "body": r[4],
                "status": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
        )
    return out


def insert_recommendation(
    db: Session,
    schema: str,
    campaign_id: UUID | None,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any],
    status: str = "pending",
) -> UUID:
    _set_path(db, schema)
    rid = uuid.uuid4()
    db.execute(
        text(
            f'''
INSERT INTO "{schema}".recommendations (id, campaign_id, kind, title, body, payload, status, created_at)
VALUES (:id, :cid, :k, :t, :b, :p, :s, NOW())
'''
        ),
        {
            "id": str(rid),
            "cid": str(campaign_id) if campaign_id else None,
            "k": kind,
            "t": title,
            "b": body,
            "p": json.dumps(payload, ensure_ascii=False),
            "s": status,
        },
    )
    db.commit()
    return rid


def pending_recommendations(db: Session, schema: str, campaign_uuid: UUID) -> list[dict[str, Any]]:
    _set_path(db, schema)
    rows = db.execute(
        text(
            f'''
SELECT id, kind, title, body, payload FROM "{schema}".recommendations
WHERE campaign_id = :cid AND status = 'pending'
ORDER BY created_at DESC
'''
        ),
        {"cid": str(campaign_uuid)},
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": str(r[0]),
                "kind": r[1],
                "title": r[2],
                "body": r[3],
                "payload": json.loads(r[4] or "{}"),
            }
        )
    return out


def mark_recommendations_applied(db: Session, schema: str, ids: list[UUID]) -> None:
    if not ids:
        return
    _set_path(db, schema)
    for rid in ids:
        db.execute(
            text(f'UPDATE "{schema}".recommendations SET status = \'applied\' WHERE id = :id'),
            {"id": str(rid)},
        )
    db.commit()


def insert_agent_log(
    db: Session,
    schema: str,
    campaign_id: UUID | None,
    level: str,
    message: str,
    details: dict[str, Any],
) -> None:
    _set_path(db, schema)
    lid = uuid.uuid4()
    db.execute(
        text(
            f'''
INSERT INTO "{schema}".agent_logs (id, campaign_id, level, message, details, created_at)
VALUES (:id, :cid, :lvl, :msg, :d, NOW())
'''
        ),
        {
            "id": str(lid),
            "cid": str(campaign_id) if campaign_id else None,
            "lvl": level,
            "msg": message,
            "d": json.dumps(details, ensure_ascii=False),
        },
    )
    db.commit()


def list_agent_logs(db: Session, schema: str, campaign_uuid: UUID | None, limit: int) -> list[dict[str, Any]]:
    _set_path(db, schema)
    if campaign_uuid:
        rows = db.execute(
            text(
                f'''
SELECT id, campaign_id, level, message, details, created_at FROM "{schema}".agent_logs
WHERE campaign_id = :cid
ORDER BY created_at DESC
LIMIT :lim
'''
            ),
            {"cid": str(campaign_uuid), "lim": limit},
        ).fetchall()
    else:
        rows = db.execute(
            text(
                f'''
SELECT id, campaign_id, level, message, details, created_at FROM "{schema}".agent_logs
ORDER BY created_at DESC
LIMIT :lim
'''
            ),
            {"lim": limit},
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": str(r[0]),
                "campaign_id": str(r[1]) if r[1] else None,
                "level": r[2],
                "message": r[3],
                "details": json.loads(r[4] or "{}"),
                "created_at": r[5].isoformat() if r[5] else None,
            }
        )
    return out


def list_all_campaign_modes(db: Session, schema: str) -> list[tuple[UUID, str, int]]:
    _set_path(db, schema)
    rows = db.execute(
        text(f'SELECT id, mode, yandex_campaign_id FROM "{schema}".campaigns')
    ).fetchall()
    return [(UUID(str(r[0])), str(r[1]), int(r[2])) for r in rows]


def recommendations_analytics(
    db: Session,
    schema: str,
    *,
    campaign_id: UUID | None = None,
    status: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    _set_path(db, schema)
    q = f'''
SELECT
  r.id,
  r.campaign_id,
  c.name AS campaign_name,
  r.kind,
  r.title,
  r.body,
  r.status,
  r.created_at
FROM "{schema}".recommendations r
LEFT JOIN "{schema}".campaigns c ON c.id = r.campaign_id
WHERE 1=1
'''
    params: dict[str, Any] = {"lim": limit}
    if campaign_id:
        q += " AND r.campaign_id = :campaign_id"
        params["campaign_id"] = str(campaign_id)
    if status:
        q += " AND r.status = :status"
        params["status"] = status
    if kind:
        q += " AND r.kind = :kind"
        params["kind"] = kind
    if search:
        q += " AND (r.title ILIKE :s OR r.body ILIKE :s OR COALESCE(c.name,'') ILIKE :s)"
        params["s"] = f"%{search}%"
    q += " ORDER BY r.created_at DESC LIMIT :lim"

    rows = db.execute(text(q), params).fetchall()
    return [
        {
            "id": str(r[0]),
            "campaign_id": str(r[1]) if r[1] else None,
            "campaign_name": r[2],
            "kind": r[3],
            "title": r[4],
            "body": r[5],
            "status": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]

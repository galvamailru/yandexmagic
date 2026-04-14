from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.public import TenantYandexToken
from app.repositories import tenant_queries as tq
from app.services import yandex_direct


async def sync_campaigns_from_yandex(db: Session, tenant_schema: str, access_token: str) -> list[dict[str, Any]]:
    rows = await yandex_direct.campaigns_get(access_token)
    for c in rows:
        cid = int(c.get("Id"))
        name = str(c.get("Name") or "")
        state = str(c.get("State") or "")
        tq.upsert_campaign(db, tenant_schema, cid, name, state, mode="monitoring")
    return tq.list_campaigns(db, tenant_schema)


async def pull_stats_for_tenant(db: Session, tenant_schema: str, access_token: str) -> None:
    camps = tq.list_campaigns(db, tenant_schema)
    if not camps:
        return
    ids = [int(c["yandex_campaign_id"]) for c in camps]
    day_to = date.today()
    day_from = day_to - timedelta(days=7)
    rows = await yandex_direct.reports_campaign_daily(access_token, ids, day_from, day_to)
    if not rows:
        # Fallback: one synthetic row per campaign for chart when Reports empty
        for c in camps:
            cid = UUID(c["id"])
            tq.insert_daily_stat(
                db,
                tenant_schema,
                cid,
                day_to,
                Decimal("0"),
                0,
                0,
                0.0,
                None,
            )
        return
    by_camp: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_camp.setdefault(int(r["CampaignId"]), []).append(r)
    yandex_to_local = {int(c["yandex_campaign_id"]): UUID(c["id"]) for c in camps}
    for yid, items in by_camp.items():
        local_id = yandex_to_local.get(yid)
        if not local_id:
            continue
        for it in items:
            d = date.fromisoformat(str(it["Date"])[:10])
            raw = Decimal(str(it.get("Cost") or 0))
            cost = raw / Decimal("1000000") if raw > Decimal("100000") else raw
            clicks = int(it.get("Clicks") or 0)
            impr = int(it.get("Impressions") or 0)
            ctr = float(clicks / impr) if impr else 0.0
            avg_cpc = (cost / Decimal(clicks)) if clicks else None
            tq.insert_daily_stat(db, tenant_schema, local_id, d, cost, clicks, impr, ctr, avg_cpc)


def get_access_token_for_tenant(db: Session, tenant_id: UUID) -> str | None:
    tok = db.query(TenantYandexToken).filter(TenantYandexToken.tenant_id == tenant_id).first()
    return tok.access_token if tok else None

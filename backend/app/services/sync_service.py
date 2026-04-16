from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.public import TenantYandexToken
from app.config import get_settings
from app.repositories import tenant_queries as tq
from app.services import yandex_direct
from app.services.crypto_service import decrypt_text, encrypt_text
from app.services.yandex_oauth import refresh_access_token

settings = get_settings()


async def sync_campaigns_from_yandex(db: Session, tenant_schema: str, access_token: str) -> list[dict[str, Any]]:
    tenant_token = db.query(TenantYandexToken).filter(TenantYandexToken.tenant.has(schema_name=tenant_schema)).first()
    client_login = tenant_token.client_login if tenant_token else None
    rows, meta = await yandex_direct.campaigns_get_with_meta(access_token, client_login=client_login)
    level = "info"
    message = "Синхронизация кампаний из Yandex Direct выполнена"
    if int(meta.get("count") or 0) == 0:
        level = "warning"
        message = "Синхронизация кампаний: пустой ответ или ошибка"
    tq.insert_agent_log(
        db,
        tenant_schema,
        None,
        level,
        message,
        {
            "source": meta.get("source"),
            "http_status": meta.get("http_status"),
            "count": meta.get("count"),
            "error": meta.get("error"),
            "sandbox_mode": settings.YANDEX_SANDBOX,
        },
    )
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
    tenant_token = db.query(TenantYandexToken).filter(TenantYandexToken.tenant.has(schema_name=tenant_schema)).first()
    client_login = tenant_token.client_login if tenant_token else None
    rows = await yandex_direct.reports_campaign_daily(access_token, ids, day_from, day_to, client_login=client_login)
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
    if not tok:
        return None
    access = decrypt_text(tok.access_token)
    if not access:
        return None
    return access


def get_client_login_for_tenant(db: Session, tenant_id: UUID) -> str | None:
    tok = db.query(TenantYandexToken).filter(TenantYandexToken.tenant_id == tenant_id).first()
    if not tok:
        return None
    value = (tok.client_login or "").strip()
    return value or None


def set_client_login_for_tenant(db: Session, tenant_id: UUID, client_login: str | None) -> None:
    tok = db.query(TenantYandexToken).filter(TenantYandexToken.tenant_id == tenant_id).first()
    if not tok:
        return
    tok.client_login = (client_login or "").strip() or None
    db.add(tok)
    db.commit()


async def ensure_valid_access_token(db: Session, tenant_id: UUID) -> str | None:
    tok = db.query(TenantYandexToken).filter(TenantYandexToken.tenant_id == tenant_id).first()
    if not tok:
        return None
    access = decrypt_text(tok.access_token)
    if not access:
        return None
    if tok.expires_at and tok.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
        refresh = decrypt_text(tok.refresh_token)
        if refresh:
            try:
                refreshed = await refresh_access_token(refresh)
                new_access = str(refreshed.get("access_token") or access)
                tok.access_token = encrypt_text(new_access)
                if refreshed.get("refresh_token"):
                    tok.refresh_token = encrypt_text(str(refreshed["refresh_token"]))
                if refreshed.get("expires_in"):
                    tok.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(refreshed["expires_in"]))
                db.add(tok)
                db.commit()
                return new_access
            except Exception:  # noqa: BLE001
                return access
    return access

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_tenant_access, require_tenant_manager_or_owner
from app.models.public import Tenant, User
from app.repositories import tenant_queries as tq
from app.schemas.common import (
    ActionHistoryOut,
    AgentSettingsOut,
    AgentSettingsUpdate,
    AgentLogOut,
    CampaignDetailOut,
    CampaignModeBody,
    CampaignOut,
    CampaignRecommendationOut,
    RecommendationBulkApplyBody,
    RecommendationBulkStatusBody,
    CampaignStateBody,
    CampaignStatsOut,
)
from app.services import sync_service
from app.services import yandex_direct
from app.services.openai_service import generate_recommendations
from app.services.request_context import get_correlation_id

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _page_params(page: int, limit: int) -> tuple[int, int]:
    p = max(1, page)
    lim = min(max(1, limit), 100)
    return p, lim


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> list[CampaignOut]:
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected for tenant")
    await sync_service.sync_campaigns_from_yandex(db, tenant.schema_name, token)
    rows = tq.list_campaigns(db, tenant.schema_name)
    return [CampaignOut(**r) for r in rows]  # type: ignore[arg-type]


@router.patch("/{campaign_id}/mode")
def set_mode(
    campaign_id: UUID,
    body: CampaignModeBody,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    user: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> CampaignOut:
    if body.mode == "autopilot" and not user.autopilot_risk_accepted_at:
        raise HTTPException(status_code=400, detail="Autopilot requires risk acceptance")
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tq.update_campaign_mode(db, tenant.schema_name, campaign_id, body.mode)
    c2 = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    assert c2
    return CampaignOut(**c2)


@router.patch("/{campaign_id}/state")
async def set_state(
    campaign_id: UUID,
    body: CampaignStateBody,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    user: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> CampaignOut:
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    yc_id = int(c["yandex_campaign_id"])
    ok = await (yandex_direct.campaigns_resume(token, [yc_id]) if body.state == "ON" else yandex_direct.campaigns_suspend(token, [yc_id]))
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to update campaign state in Yandex Direct")
    tq.update_campaign_state(db, tenant.schema_name, campaign_id, body.state)
    corr = get_correlation_id()
    tq.insert_action_history(
        db,
        tenant.schema_name,
        campaign_id,
        "campaign_state_change",
        {"state": c["state"]},
        {"state": body.state, "actor_user_id": str(user.id)},
        corr,
    )
    updated = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    assert updated
    return CampaignOut(**updated)


@router.get("/by-id/{campaign_id}", response_model=CampaignDetailOut)
def campaign_detail(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    include_related: bool = False,
) -> CampaignDetailOut:
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    stats = tq.campaign_daily_stats(db, tenant.schema_name, campaign_id, limit=30)
    recs = tq.campaign_recommendations(db, tenant.schema_name, campaign_id, limit=30) if include_related else []
    logs = tq.list_agent_logs(db, tenant.schema_name, campaign_id, limit=30) if include_related else []
    return CampaignDetailOut(
        campaign=CampaignOut(**c),
        stats=[CampaignStatsOut(**s) for s in stats],
        recommendations=[
            CampaignRecommendationOut(
                id=r["id"],  # type: ignore[arg-type]
                kind=r["kind"],
                title=r["title"],
                body=r["body"],
                payload=r["payload"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in recs
        ],
        logs=[
            AgentLogOut(
                id=UUID(r["id"]),
                campaign_id=UUID(r["campaign_id"]) if r.get("campaign_id") else None,
                level=r["level"],
                message=r["message"],
                details=r["details"],
                created_at=r["created_at"],
            )
            for r in logs
        ],
    )




@router.post("/{campaign_id}/recommendations/generate")
async def generate_recs(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict[str, str]:
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    summary = f"Кампания {c['name']} (yandex id {c['yandex_campaign_id']}), режим советник."
    items = generate_recommendations(summary, db=db)
    for it in items:
        tq.insert_recommendation(
            db,
            tenant.schema_name,
            campaign_id,
            str(it.get("kind", "general")),
            str(it.get("title", "")),
            str(it.get("body", "")),
            dict(it.get("payload") or {}),
        )
    tq.insert_agent_log(
        db,
        tenant.schema_name,
        campaign_id,
        "info",
        "Сгенерированы рекомендации AI",
        {"count": len(items)},
    )
    return {"status": "ok", "count": str(len(items))}


@router.post("/{campaign_id}/recommendations/apply-all")
async def apply_all(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    user: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict[str, str]:
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    pending = tq.pending_recommendations(db, tenant.schema_name, campaign_id)
    applied_ids: list[UUID] = []
    corr = get_correlation_id()
    for p in pending:
        payload = p.get("payload") or {}
        kid = int(payload.get("keyword_id") or 0)
        action = str(payload.get("action") or "")
        if kid and action == "suspend":
            await yandex_direct.keywords_suspend(token, [kid])
            tq.insert_action_history(
                db,
                tenant.schema_name,
                campaign_id,
                "suspend_keyword",
                {"keyword_id": kid, "status": "ON"},
                    {"keyword_id": kid, "status": "SUSPENDED", "actor_user_id": str(user.id)},
                corr,
            )
        elif kid and action == "bid_up":
            bid = float(payload.get("new_bid_rub") or 0)
            if bid > 0:
                await yandex_direct.keywords_set_bids(token, [{"KeywordId": kid, "Bid": int(bid * 1_000_000)}])
                tq.insert_action_history(
                    db,
                    tenant.schema_name,
                    campaign_id,
                    "set_bid",
                    {"keyword_id": kid},
                    {"keyword_id": kid, "bid_rub": bid, "actor_user_id": str(user.id)},
                    corr,
                )
        applied_ids.append(UUID(str(p["id"])))
    tq.mark_recommendations_applied(db, tenant.schema_name, applied_ids)
    tq.insert_agent_log(
        db,
        tenant.schema_name,
        campaign_id,
        "info",
        "Применены рекомендации",
        {"applied": len(applied_ids)},
    )
    return {"status": "ok", "applied": str(len(applied_ids))}


@router.post("/{campaign_id}/recommendations/bulk-status")
async def recommendations_bulk_status(
    campaign_id: UUID,
    body: RecommendationBulkStatusBody,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict[str, str]:
    changed = tq.update_recommendations_status(db, tenant.schema_name, body.recommendation_ids, body.status)
    tq.insert_agent_log(
        db,
        tenant.schema_name,
        campaign_id,
        "info",
        "Обновлены статусы рекомендаций",
        {"changed": changed, "status": body.status},
    )
    return {"status": "ok", "changed": str(changed)}


@router.post("/{campaign_id}/recommendations/apply-selected")
async def apply_selected(
    campaign_id: UUID,
    body: RecommendationBulkApplyBody,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    user: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict[str, str]:
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    pending = tq.recommendations_by_ids(db, tenant.schema_name, campaign_id, body.recommendation_ids)
    applied_ids: list[UUID] = []
    corr = get_correlation_id()
    for p in pending:
        if p.get("status") != "pending":
            continue
        payload = p.get("payload") or {}
        kid = int(payload.get("keyword_id") or 0)
        action = str(payload.get("action") or "")
        if kid and action == "suspend":
            await yandex_direct.keywords_suspend(token, [kid])
            tq.insert_action_history(
                db,
                tenant.schema_name,
                campaign_id,
                "suspend_keyword",
                {"keyword_id": kid, "status": "ON"},
                {"keyword_id": kid, "status": "SUSPENDED", "actor_user_id": str(user.id)},
                corr,
            )
        elif kid and action == "bid_up":
            bid = float(payload.get("new_bid_rub") or 0)
            if bid > 0:
                await yandex_direct.keywords_set_bids(token, [{"KeywordId": kid, "Bid": int(bid * 1_000_000)}])
                tq.insert_action_history(
                    db,
                    tenant.schema_name,
                    campaign_id,
                    "set_bid",
                    {"keyword_id": kid},
                    {"keyword_id": kid, "bid_rub": bid, "actor_user_id": str(user.id)},
                    corr,
                )
        applied_ids.append(UUID(str(p["id"])))
    tq.mark_recommendations_applied(db, tenant.schema_name, applied_ids)
    tq.insert_agent_log(
        db,
        tenant.schema_name,
        campaign_id,
        "info",
        "Применены выбранные рекомендации",
        {"applied": len(applied_ids)},
    )
    return {"status": "ok", "applied": str(len(applied_ids))}


@router.get("/agent-settings", response_model=AgentSettingsOut)
def get_agent_settings(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> AgentSettingsOut:
    return AgentSettingsOut(**tq.get_agent_settings(db, tenant.schema_name))


@router.put("/agent-settings", response_model=AgentSettingsOut)
def update_agent_settings(
    body: AgentSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> AgentSettingsOut:
    tq.update_agent_settings(
        db,
        tenant.schema_name,
        {
            "ctr_low_threshold": body.ctr_low_threshold,
            "ctr_high_threshold": body.ctr_high_threshold,
            "cost_threshold_rub": body.cost_threshold_rub,
            "bid_up_factor": body.bid_up_factor,
            "autopilot_dry_run": body.autopilot_dry_run,
            "max_changes_per_cycle": body.max_changes_per_cycle,
        },
    )
    return AgentSettingsOut(**tq.get_agent_settings(db, tenant.schema_name))


@router.get("/{campaign_id}/autopilot-preview")
async def autopilot_preview(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> dict[str, list[dict[str, object]]]:
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    rows = await yandex_direct.keyword_performance_rows(token, [int(c["yandex_campaign_id"])])
    cfg = tq.get_agent_settings(db, tenant.schema_name)
    items: list[dict[str, object]] = []
    for r in rows:
        kid = int(r.get("Id") or 0)
        ctr = float(r.get("Ctr") or 0)
        cost = float(r.get("Cost") or 0)
        bid = float(r.get("Bid") or 0)
        if ctr < cfg["ctr_low_threshold"] and cost > cfg["cost_threshold_rub"]:
            items.append({"keyword_id": kid, "keyword": r.get("Keyword"), "action": "suspend"})
        elif ctr > cfg["ctr_high_threshold"]:
            items.append(
                {
                    "keyword_id": kid,
                    "keyword": r.get("Keyword"),
                    "action": "bid_up",
                    "new_bid_rub": round(bid * cfg["bid_up_factor"], 2),
                }
            )
    return {"preview": items[: cfg["max_changes_per_cycle"]]}


@router.get("/{campaign_id}/action-history")
def action_history(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    page: int = 1,
    limit: int = 20,
) -> dict:
    page, limit = _page_params(page, limit)
    rows, total = tq.recent_action_history_paged(
        db, tenant.schema_name, campaign_id=campaign_id, limit=limit, offset=(page - 1) * limit
    )
    return {
        "items": [ActionHistoryOut(**r).model_dump() for r in rows],  # type: ignore[arg-type]
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/{campaign_id}/undo-last")
async def undo_last_action(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict[str, str]:
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    rows = tq.recent_action_history(db, tenant.schema_name, campaign_id=campaign_id, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No actions to rollback")
    last = rows[0]
    action_type = last["action_type"]
    before = last["payload_before"]
    if action_type == "suspend_keyword":
        kid = int(before.get("keyword_id") or 0)
        if kid:
            await yandex_direct.keywords_resume(token, [kid])
    elif action_type == "set_bid":
        kid = int(before.get("keyword_id") or 0)
        bid = float(before.get("bid_rub") or 0)
        if kid and bid > 0:
            await yandex_direct.keywords_set_bids(token, [{"KeywordId": kid, "Bid": int(bid * 1_000_000)}])
    tq.insert_agent_log(
        db,
        tenant.schema_name,
        campaign_id,
        "info",
        "Выполнен rollback последнего действия",
        {"rolled_back_action": action_type, "source_action_id": last["id"]},
    )
    return {"status": "ok"}


@router.get("/{campaign_id}/logs")
def campaign_logs(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    page: int = 1,
    limit: int = 20,
) -> dict:
    page, limit = _page_params(page, limit)
    rows, total = tq.list_agent_logs_paged(
        db, tenant.schema_name, campaign_id, limit=limit, offset=(page - 1) * limit
    )
    return {
        "items": [
            AgentLogOut(
                id=UUID(r["id"]),
                campaign_id=UUID(r["campaign_id"]) if r.get("campaign_id") else None,
                level=r["level"],
                message=r["message"],
                details=r["details"],
                created_at=r["created_at"],
            ).model_dump()
            for r in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{campaign_id}/recommendations")
def campaign_recommendations(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    page: int = 1,
    limit: int = 20,
) -> dict:
    page, limit = _page_params(page, limit)
    rows, total = tq.campaign_recommendations_paged(
        db, tenant.schema_name, campaign_id, limit=limit, offset=(page - 1) * limit
    )
    return {
        "items": [
            CampaignRecommendationOut(
                id=r["id"],  # type: ignore[arg-type]
                kind=r["kind"],
                title=r["title"],
                body=r["body"],
                payload=r["payload"],
                status=r["status"],
                created_at=r["created_at"],
            ).model_dump()
            for r in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{campaign_id}/keywords")
async def campaign_keywords(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    page: int = 1,
    limit: int = 20,
) -> dict:
    page, limit = _page_params(page, limit)
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    rows = await yandex_direct.keyword_performance_rows(token, [int(c["yandex_campaign_id"])])
    items = [
        {
            "id": int(r.get("Id") or 0),
            "keyword": str(r.get("Keyword") or ""),
            "state": str(r.get("UserParam1") or r.get("Status") or "UNKNOWN"),
            "bid_rub": float(r.get("Bid") or 0),
            "cost_rub": float(r.get("Cost") or 0),
            "ctr": float(r.get("Ctr") or 0),
        }
        for r in rows
    ]
    total = len(items)
    start = (page - 1) * limit
    return {"items": items[start : start + limit], "total": total, "page": page, "limit": limit}


@router.get("/{campaign_id}/ads")
async def campaign_ads(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    page: int = 1,
    limit: int = 20,
) -> dict:
    page, limit = _page_params(page, limit)
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    token = await sync_service.ensure_valid_access_token(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    rows = await yandex_direct.ad_performance_rows(token, [int(c["yandex_campaign_id"])])
    items = [
        {
            "id": int(r.get("Id") or 0),
            "title": str(r.get("Title") or ""),
            "state": str(r.get("State") or "UNKNOWN"),
            "cost_rub": float(r.get("Cost") or 0),
            "clicks": int(r.get("Clicks") or 0),
            "impressions": int(r.get("Impressions") or 0),
        }
        for r in rows
    ]
    total = len(items)
    start = (page - 1) * limit
    return {"items": items[start : start + limit], "total": total, "page": page, "limit": limit}

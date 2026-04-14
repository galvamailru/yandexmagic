from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_tenant_access
from app.models.public import Tenant, User
from app.repositories import tenant_queries as tq
from app.schemas.common import AgentLogOut, CampaignModeBody, CampaignOut
from app.services import sync_service
from app.services import yandex_direct
from app.services.openai_service import generate_recommendations

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> list[CampaignOut]:
    token = sync_service.get_access_token_for_tenant(db, tenant.id)
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
    user: Annotated[User, Depends(get_current_user)],
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


@router.post("/{campaign_id}/recommendations/generate")
async def generate_recs(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> dict[str, str]:
    c = tq.get_campaign_by_id(db, tenant.schema_name, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    summary = f"Кампания {c['name']} (yandex id {c['yandex_campaign_id']}), режим советник."
    items = generate_recommendations(summary)
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
) -> dict[str, str]:
    token = sync_service.get_access_token_for_tenant(db, tenant.id)
    if not token:
        raise HTTPException(status_code=400, detail="Yandex not connected")
    pending = tq.pending_recommendations(db, tenant.schema_name, campaign_id)
    applied_ids: list[UUID] = []
    for p in pending:
        payload = p.get("payload") or {}
        kid = int(payload.get("keyword_id") or 0)
        action = str(payload.get("action") or "")
        if kid and action == "suspend":
            await yandex_direct.keywords_suspend(token, [kid])
        elif kid and action == "bid_up":
            bid = float(payload.get("new_bid_rub") or 0)
            if bid > 0:
                await yandex_direct.keywords_set_bids(token, [{"KeywordId": kid, "Bid": int(bid * 1_000_000)}])
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


@router.get("/{campaign_id}/logs", response_model=list[AgentLogOut])
def campaign_logs(
    campaign_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    limit: int = 100,
) -> list[AgentLogOut]:
    rows = tq.list_agent_logs(db, tenant.schema_name, campaign_id, limit=limit)
    return [
        AgentLogOut(
            id=UUID(r["id"]),
            campaign_id=UUID(r["campaign_id"]) if r.get("campaign_id") else None,
            level=r["level"],
            message=r["message"],
            details=r["details"],
            created_at=r["created_at"],
        )
        for r in rows
    ]

import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_tenant_access, require_tenant_manager_or_owner
from app.models.public import Tenant, User
from app.repositories import tenant_queries as tq
from app.schemas.common import WizardLaunchBody, WizardStep1, WizardStep2Result, WizardStep3Body
from app.services import site_scraper, wordstat
from app.services.sync_service import ensure_valid_access_token
from app.services.openai_service import generate_ad_texts
from app.services.wizard_store import get_wizard, upsert_wizard
from app.services import yandex_direct

router = APIRouter(prefix="/wizard", tags=["wizard"])


@router.post("/step1")
def step1(
    body: WizardStep1,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict:
    payload = {
        "site_url": body.site_url,
        "budget_rub": body.budget_rub,
        "geo": body.geo,
        "goal": body.goal,
    }
    upsert_wizard(db, tenant.id, 1, payload)
    return {"ok": True, "step": 2}


@router.post("/step2", response_model=WizardStep2Result)
async def step2(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> WizardStep2Result:
    w = get_wizard(db, tenant.id)
    if not w or not w.get("payload"):
        raise HTTPException(status_code=400, detail="Сначала заполните шаг 1")
    p = w["payload"]
    url = str(p.get("site_url", ""))

    title, text = await asyncio.to_thread(site_scraper.fetch_page_text, url)
    seed = [title, *text.split()[:40]]
    phrases = list({s.strip() for s in seed if len(s.strip()) > 2})[:15]
    access_token = await ensure_valid_access_token(db, tenant.id)
    ws = await wordstat.top_requests(phrases, access_token=access_token)
    keywords = [str(x.get("phrase")) for x in ws if x.get("phrase")]
    if not keywords:
        keywords = phrases[:10]

    groups: list[list[str]] = []
    for i in range(0, len(keywords), 5):
        groups.append(keywords[i : i + 5])

    summary = f"{title}. {text[:2000]}"
    ads = generate_ad_texts(summary, keywords)

    payload = {**p, "keywords": keywords, "groups": groups, "ads": ads}
    upsert_wizard(db, tenant.id, 2, payload)
    return WizardStep2Result(keywords=keywords, groups=groups, ads=ads)


@router.post("/step3")
def step3(
    body: WizardStep3Body,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    _: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict:
    w = get_wizard(db, tenant.id)
    if not w or not w.get("payload"):
        raise HTTPException(status_code=400, detail="Нет данных мастера")
    p = w["payload"]
    p["ads"] = body.ads
    upsert_wizard(db, tenant.id, 3, p)
    return {"ok": True, "step": 4}


@router.post("/launch")
async def launch(
    body: WizardLaunchBody,
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    user: Annotated[User, Depends(require_tenant_manager_or_owner)],
) -> dict:
    if not body.accept_autopilot_risk:
        raise HTTPException(status_code=400, detail="Нужно подтвердить риски автопилота")
    user.autopilot_risk_accepted_at = datetime.now(timezone.utc)
    db.add(user)

    access_token = await ensure_valid_access_token(db, tenant.id)
    if not access_token:
        raise HTTPException(status_code=400, detail="Нет OAuth-токена Директа")
    w = get_wizard(db, tenant.id)
    if not w or not w.get("payload"):
        raise HTTPException(status_code=400, detail="Мастер не завершён")
    p = w["payload"]
    name = f"YandexMagic — {p.get('site_url', 'кампания')}"[:255]
    spec = {
        "Name": name,
        "DailyBudget": int(float(p.get("budget_rub", 0)) * 1_000_000),
        "StartDate": __import__("datetime").date.today().isoformat(),
        "TextCampaign": {"BiddingStrategy": {"Search": {"BiddingStrategyType": "SERVING_OFF"}}},
    }
    yid = await yandex_direct.campaigns_add(access_token, spec)
    if not yid:
        raise HTTPException(status_code=502, detail="Не удалось создать кампанию в Директе")
    local = tq.upsert_campaign(db, tenant.schema_name, int(yid), name, "ON", mode="autopilot")
    tq.insert_agent_log(
        db,
        tenant.schema_name,
        local,
        "info",
        "Кампания создана мастером и переведена в режим автопилота",
        {"yandex_campaign_id": yid},
    )
    db.commit()
    return {"ok": True, "yandex_campaign_id": yid, "campaign_id": str(local)}

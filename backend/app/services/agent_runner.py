from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.public import Tenant, TenantMembership, User
from app.repositories import tenant_queries as tq
from app.services import yandex_direct
from app.services.openai_service import generate_recommendations
from app.services.sync_service import get_access_token_for_tenant, pull_stats_for_tenant, sync_campaigns_from_yandex


def _tenant_user_with_risk(db: Session, tenant_id: UUID) -> User | None:
    m = db.query(TenantMembership).filter(TenantMembership.tenant_id == tenant_id).first()
    if not m:
        return None
    u = db.query(User).filter(User.id == m.user_id).first()
    if u and u.autopilot_risk_accepted_at:
        return u
    return None


async def run_for_tenant(db: Session, tenant: Tenant) -> None:
    if tenant.is_blocked:
        return
    token = get_access_token_for_tenant(db, tenant.id)
    if not token:
        return
    await sync_campaigns_from_yandex(db, tenant.schema_name, token)
    await pull_stats_for_tenant(db, tenant.schema_name, token)

    modes = tq.list_all_campaign_modes(db, tenant.schema_name)
    yandex_to_local = {m[2]: (m[0], m[1]) for m in modes}
    yandex_ids = list(yandex_to_local.keys())
    if not yandex_ids:
        return
    kw_rows = await yandex_direct.keyword_performance_rows(token, yandex_ids)

    for yid, (local_id, mode) in yandex_to_local.items():
        if mode != "advisor":
            continue
        rows = [r for r in kw_rows if int(r.get("CampaignId") or 0) == yid]
        if not rows:
            continue
        lines = [
            f"- {r.get('Keyword')}: CTR={float(r.get('Ctr') or 0):.2f}%, "
            f"расход={float(r.get('Cost') or 0):.2f} ₽, id={r.get('Id')}"
            for r in rows[:50]
        ]
        summary = "Статистика по ключевым фразам:\n" + "\n".join(lines)
        items = generate_recommendations(summary)
        for it in items:
            pl = dict(it.get("payload") or {})
            tq.insert_recommendation(
                db,
                tenant.schema_name,
                local_id,
                str(it.get("kind", "general")),
                str(it.get("title", "Рекомендация")),
                str(it.get("body", "")),
                pl,
            )
        tq.insert_agent_log(
            db,
            tenant.schema_name,
            local_id,
            "info",
            "Советник: сгенерированы рекомендации",
            {"count": len(items)},
        )

    risk_user = _tenant_user_with_risk(db, tenant.id)
    has_autopilot = any(m[1] == "autopilot" for m in modes)
    if has_autopilot and not risk_user:
        tq.insert_agent_log(
            db,
            tenant.schema_name,
            None,
            "warning",
            "Автопилот не выполнялся: нет подтверждения рисков у пользователя тенанта",
            {},
        )
        return

    for row in kw_rows:
        yid = int(row.get("CampaignId") or 0)
        if yid not in yandex_to_local:
            continue
        local_id, mode = yandex_to_local[yid]
        if mode != "autopilot":
            continue
        kid = int(row.get("Id") or 0)
        ctr = float(row.get("Ctr") or 0)
        cost = float(row.get("Cost") or 0)
        bid = float(row.get("Bid") or 0)
        if ctr < 1.0 and cost > 500 and kid:
            await yandex_direct.keywords_suspend(token, [kid])
            tq.insert_agent_log(
                db,
                tenant.schema_name,
                local_id,
                "info",
                f"Автопилот: отключена фраза «{row.get('Keyword')}»",
                {"keyword_id": kid, "action": "suspend"},
            )
        elif ctr > 5.0 and kid:
            new_bid = bid * 1.1
            await yandex_direct.keywords_set_bids(
                token,
                [{"KeywordId": kid, "Bid": int(new_bid * 1_000_000)}],
            )
            tq.insert_agent_log(
                db,
                tenant.schema_name,
                local_id,
                "info",
                f"Автопилот: повышена ставка для «{row.get('Keyword')}»",
                {"keyword_id": kid, "new_bid_rub": new_bid},
            )

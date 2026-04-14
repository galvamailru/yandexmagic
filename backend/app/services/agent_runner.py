from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.public import Tenant, TenantMembership, User
from app.repositories import tenant_queries as tq
from app.services.notifier import send_alert
from app.services.request_context import get_correlation_id
from app.services import yandex_direct
from app.services.openai_service import generate_recommendations
from app.services.sync_service import (
    ensure_valid_access_token,
    get_client_login_for_tenant,
    pull_stats_for_tenant,
    sync_campaigns_from_yandex,
)

settings = get_settings()


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
    token = await ensure_valid_access_token(db, tenant.id)
    if not token:
        return
    client_login = get_client_login_for_tenant(db, tenant.id)
    await sync_campaigns_from_yandex(db, tenant.schema_name, token)
    await pull_stats_for_tenant(db, tenant.schema_name, token)

    modes = tq.list_all_campaign_modes(db, tenant.schema_name)
    cfg = tq.get_agent_settings(db, tenant.schema_name)
    yandex_to_local = {m[2]: (m[0], m[1]) for m in modes}
    yandex_ids = list(yandex_to_local.keys())
    if not yandex_ids:
        return
    kw_rows = await yandex_direct.keyword_performance_rows(token, yandex_ids, client_login=client_login)

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
        items = generate_recommendations(summary, db=db)
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

    changes_done = 0
    max_changes = min(int(cfg["max_changes_per_cycle"]), settings.AUTOPILOT_MAX_CHANGES_PER_CYCLE)
    for row in kw_rows:
        yid = int(row.get("CampaignId") or 0)
        if yid not in yandex_to_local:
            continue
        local_id, mode = yandex_to_local[yid]
        if mode != "autopilot":
            continue
        if changes_done >= max_changes:
            break
        kid = int(row.get("Id") or 0)
        ctr = float(row.get("Ctr") or 0)
        cost = float(row.get("Cost") or 0)
        bid = float(row.get("Bid") or 0)
        low_ctr = float(cfg["ctr_low_threshold"])
        high_ctr = float(cfg["ctr_high_threshold"])
        cost_thr = float(cfg["cost_threshold_rub"])
        factor = float(cfg["bid_up_factor"])
        dry_run = bool(cfg["autopilot_dry_run"])
        corr = get_correlation_id()

        if ctr < low_ctr and cost > cost_thr and kid:
            if not dry_run:
                await yandex_direct.keywords_suspend(token, [kid], client_login=client_login)
            tq.insert_agent_log(
                db,
                tenant.schema_name,
                local_id,
                "info",
                f"Автопилот{'(dry-run)' if dry_run else ''}: отключена фраза «{row.get('Keyword')}»",
                {"keyword_id": kid, "action": "suspend", "dry_run": dry_run, "correlation_id": corr},
            )
            tq.insert_action_history(
                db,
                tenant.schema_name,
                local_id,
                "suspend_keyword",
                {"keyword_id": kid, "status": "ON"},
                {"keyword_id": kid, "status": "SUSPENDED"},
                corr,
            )
            changes_done += 1
        elif ctr > high_ctr and kid:
            new_bid = bid * factor
            if not dry_run:
                await yandex_direct.keywords_set_bids(
                    token,
                    [{"KeywordId": kid, "Bid": int(new_bid * 1_000_000)}],
                    client_login=client_login,
                )
            tq.insert_agent_log(
                db,
                tenant.schema_name,
                local_id,
                "info",
                f"Автопилот{'(dry-run)' if dry_run else ''}: повышена ставка для «{row.get('Keyword')}»",
                {"keyword_id": kid, "new_bid_rub": new_bid, "dry_run": dry_run, "correlation_id": corr},
            )
            tq.insert_action_history(
                db,
                tenant.schema_name,
                local_id,
                "set_bid",
                {"keyword_id": kid, "bid_rub": bid},
                {"keyword_id": kid, "bid_rub": new_bid},
                corr,
            )
            changes_done += 1
        if dry_run:
            await send_alert(
                "autopilot_dry_run_preview",
                {"tenant": tenant.name, "campaign_id": str(local_id), "keyword_id": kid, "corr": corr},
            )

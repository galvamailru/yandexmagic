from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.public import Tenant, TenantMembership, User
from app.repositories import tenant_queries as tq
from app.services.notifier import send_alert
from app.services.request_context import get_correlation_id
from app.services import yandex_direct
from app.services import wordstat
from app.services.openai_service import generate_domain_actions
from app.services.agent_domains import (
    AgentAction,
    DOMAIN_AD_ROTATION,
    DOMAIN_ANOMALY_WATCHDOG,
    DOMAIN_BID_OPTIMIZATION,
    DOMAIN_BUDGET_GUARD,
    DOMAIN_KEYWORD_HYGIENE,
    DOMAIN_PRIORITY,
    DOMAIN_RETARGETING_TUNING,
)
from app.services.decision_engine import (
    actions_for_ad_rotation,
    actions_for_anomaly_watchdog,
    actions_for_bid_optimization,
    actions_for_budget_guard,
    actions_for_keyword_hygiene,
    actions_for_retargeting_tuning,
)
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

    # Unified advisor: each domain produces its own actionable recommendations.
    for domain in DOMAIN_PRIORITY:
        await run_domain_for_tenant(
            db,
            tenant,
            domain=domain,
            kw_rows=kw_rows,
            cfg=cfg,
            yandex_to_local=yandex_to_local,
            mode_filter="advisor",
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

    for domain in DOMAIN_PRIORITY:
        await run_domain_for_tenant(
            db,
            tenant,
            domain=domain,
            kw_rows=kw_rows,
            cfg=cfg,
            yandex_to_local=yandex_to_local,
            mode_filter="autopilot",
        )


async def _apply_action(
    db: Session,
    tenant: Tenant,
    token: str,
    client_login: str | None,
    action,
    dry_run: bool,
) -> bool:
    if not tq.mark_idempotency_seen(db, tenant.schema_name, action.idempotency_key):
        return False
    corr = get_correlation_id()
    local_id = UUID(action.campaign_local_id) if action.campaign_local_id else None
    ok = True
    if not dry_run:
        if action.action_type == "suspend_keyword":
            ok = await yandex_direct.keywords_suspend(token, [int(action.payload_after["keyword_id"])], client_login=client_login)
        elif action.action_type == "resume_keyword":
            ok = await yandex_direct.keywords_resume(token, [int(action.payload_after["keyword_id"])], client_login=client_login)
        elif action.action_type == "set_bid":
            ok = await yandex_direct.keywords_set_bids(
                token,
                [{"KeywordId": int(action.payload_after["keyword_id"]), "Bid": int(float(action.payload_after["bid_rub"]) * 1_000_000)}],
                client_login=client_login,
            )
        elif action.action_type == "suspend_campaign":
            ok = await yandex_direct.campaigns_suspend(
                token, [int(action.payload_after["yandex_campaign_id"])], client_login=client_login
            )
        elif action.action_type == "set_campaign_daily_budget":
            ok = await yandex_direct.campaigns_update_daily_budget(
                token,
                int(action.payload_after["yandex_campaign_id"]),
                float(action.payload_after["amount_rub"]),
                client_login=client_login,
            )
        elif action.action_type == "suspend_ad":
            ok = await yandex_direct.ads_suspend(token, [int(action.payload_after["ad_id"])], client_login=client_login)
        elif action.action_type == "resume_ad":
            ok = await yandex_direct.ads_resume(token, [int(action.payload_after["ad_id"])], client_login=client_login)
        elif action.action_type == "update_audience_bid_modifier":
            ok = await yandex_direct.audience_targets_update_bid_modifier(
                token,
                int(action.payload_after["audience_target_id"]),
                int(action.payload_after["bid_modifier_percent"]),
                client_login=client_login,
            )
        elif action.action_type == "add_negative_keywords_campaign":
            ok = await yandex_direct.campaigns_add_negative_keywords(
                token,
                int(action.payload_after["yandex_campaign_id"]),
                list(action.payload_after.get("keywords") or []),
                client_login=client_login,
            )
    if ok:
        tq.insert_action_history(
            db,
            tenant.schema_name,
            local_id,
            action.action_type,
            action.payload_before,
            action.payload_after,
            corr,
        )
        tq.insert_agent_log(
            db,
            tenant.schema_name,
            local_id,
            "info",
            f"Domain={action.domain}: применено действие {action.action_type}{' (dry-run)' if dry_run else ''}",
            {"payload_after": action.payload_after, "dry_run": dry_run, "idempotency_key": action.idempotency_key},
        )
    return ok


def _llm_actions_to_agent_actions(
    domain: str,
    campaign_local_id: str | None,
    llm_actions: list[dict],
) -> list:
    out = []
    for it in llm_actions:
        action_type = str(it.get("action_type") or "")
        params = it.get("params") if isinstance(it.get("params"), dict) else {}
        if not action_type or not params:
            continue
        before = dict(params)
        after = dict(params)
        if action_type == "suspend_keyword":
            before["status"] = "ON"
            after["status"] = "SUSPENDED"
        elif action_type == "add_negative_keywords_campaign":
            before["keywords"] = []
        out.append(
            {
                "domain": domain,
                "action_type": action_type,
                "campaign_local_id": campaign_local_id,
                "payload_before": before,
                "payload_after": after,
            }
        )
    return out


def _stable_idempotency_key(domain: str, action_type: str, campaign_local_id: str | None, payload_after: dict) -> str:
    raw = f"{domain}|{action_type}|{campaign_local_id or ''}|{str(sorted(payload_after.items()))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _action_human_text(action: AgentAction) -> tuple[str, str]:
    a = action.action_type
    p = action.payload_after
    if a == "suspend_keyword":
        return "Отключение неэффективной фразы", f"Модель предлагает отключить фразу id={p.get('keyword_id')} для снижения нецелевого расхода."
    if a == "resume_keyword":
        return "Возврат фразы в показ", f"Модель предлагает вернуть в показ фразу id={p.get('keyword_id')}."
    if a == "set_bid":
        return "Корректировка ставки", f"Модель предлагает изменить ставку по фразе id={p.get('keyword_id')} до {p.get('bid_rub')} RUB."
    if a == "suspend_campaign":
        return "Аварийная пауза кампании", f"Модель предлагает приостановить кампанию yandex_id={p.get('yandex_campaign_id')}."
    if a == "set_campaign_daily_budget":
        return "Изменение дневного бюджета", f"Модель предлагает установить дневной бюджет {p.get('amount_rub')} RUB для кампании yandex_id={p.get('yandex_campaign_id')}."
    if a == "suspend_ad":
        return "Пауза слабого объявления", f"Модель предлагает приостановить объявление id={p.get('ad_id')}."
    if a == "resume_ad":
        return "Возврат объявления в показ", f"Модель предлагает вернуть объявление id={p.get('ad_id')}."
    if a == "update_audience_bid_modifier":
        return "Корректировка по аудитории", (
            "Модель предлагает обновить корректировку аудитории "
            f"id={p.get('audience_target_id')} до {p.get('bid_modifier_percent')}%."
        )
    if a == "add_negative_keywords_campaign":
        kws = p.get("keywords") or []
        return "Добавление минус-слов", f"Модель предлагает добавить {len(kws)} минус-слов в кампанию yandex_id={p.get('yandex_campaign_id')}."
    return "Рекомендация домена", "Модель предлагает выполнить доменное действие оптимизации."


def _to_recommendation_payload(action: AgentAction) -> dict:
    return {
        "domain": action.domain,
        "action_type": action.action_type,
        **(action.payload_after or {}),
    }


async def run_domain_for_tenant(
    db: Session,
    tenant: Tenant,
    *,
    domain: str,
    mode_filter: str = "autopilot",
    kw_rows: list[dict] | None = None,
    cfg: dict | None = None,
    yandex_to_local: dict[int, tuple[UUID, str]] | None = None,
) -> int:
    if tenant.is_blocked:
        return 0
    token = await ensure_valid_access_token(db, tenant.id)
    if not token:
        return 0
    # conflict guard: only one domain run may mutate a tenant at a time
    tenant_lock_name = f"tenant-domain-lock:{tenant.id}"
    lock = db.execute(
        text(
            """
INSERT INTO job_locks(name, locked_until)
VALUES (:n, NOW() + INTERVAL '15 minutes')
ON CONFLICT (name) DO UPDATE SET locked_until = EXCLUDED.locked_until
WHERE job_locks.locked_until < NOW()
RETURNING name
"""
        ),
        {"n": tenant_lock_name},
    ).fetchone()
    db.commit()
    if not lock:
        return 0
    client_login = get_client_login_for_tenant(db, tenant.id)
    cfg = cfg or tq.get_agent_settings(db, tenant.schema_name)
    modes = tq.list_all_campaign_modes(db, tenant.schema_name)
    yandex_to_local = yandex_to_local or {m[2]: (m[0], m[1]) for m in modes}
    domain_cfg = tq.get_domain_settings(db, tenant.schema_name, domain)
    if not domain_cfg["enabled"]:
        return 0
    dry_run = bool(cfg["autopilot_dry_run"])
    max_changes = min(
        int(cfg["max_changes_per_cycle"]),
        int(domain_cfg["max_changes_per_run"]),
        settings.AUTOPILOT_MAX_CHANGES_PER_CYCLE,
    )
    if max_changes <= 0:
        return 0

    actions = []
    kw_rows = kw_rows if kw_rows is not None else await yandex_direct.keyword_performance_rows(
        token, list(yandex_to_local.keys()), client_login=client_login
    )
    llm_based_actions = []
    # one domain per run by design
    if domain == DOMAIN_KEYWORD_HYGIENE:
        for yid, (local_id, mode) in yandex_to_local.items():
            if mode != mode_filter:
                continue
            rows = [r for r in kw_rows if int(r.get("CampaignId") or 0) == yid]
            phrases = [str(r.get("Keyword") or "").strip() for r in rows if str(r.get("Keyword") or "").strip()]
            phrases = phrases[:20]
            ws_rows = await wordstat.top_requests(phrases, access_token=token)
            ws_summary = ", ".join([f"{x.get('phrase')}:{x.get('shows')}" for x in ws_rows[:20]])
            llm_summary = "keyword_hygiene rows:\n" + "\n".join(
                [
                    f"id={r.get('Id')} kw={r.get('Keyword')} ctr={r.get('Ctr')} cost={r.get('Cost')} status={r.get('Status')}"
                    for r in rows[:80]
                ]
            ) + (f"\nwordstat_top={ws_summary}" if ws_summary else "")
            llm_actions = generate_domain_actions(domain, llm_summary, db=db)
            llm_based_actions.extend(_llm_actions_to_agent_actions(domain, str(local_id), llm_actions))
            # fallback: derive negative keywords from frequent irrelevant Wordstat patterns
            stop_tokens = ("бесплатно", "скачать", "своими руками", "авито", "ozon", "wildberries", "б/у", "бу ")
            negative_candidates: list[str] = []
            for w in ws_rows:
                phrase = str(w.get("phrase") or "").lower().strip()
                if not phrase:
                    continue
                if any(tok in phrase for tok in stop_tokens):
                    negative_candidates.append(phrase)
            if negative_candidates:
                uniq = list(dict.fromkeys(negative_candidates))[:25]
                actions.append(
                    AgentAction(
                        domain=DOMAIN_KEYWORD_HYGIENE,
                        action_type="add_negative_keywords_campaign",
                        campaign_local_id=str(local_id),
                        payload_before={"yandex_campaign_id": yid, "keywords": []},
                        payload_after={"yandex_campaign_id": yid, "keywords": uniq},
                        idempotency_key=_stable_idempotency_key(
                            DOMAIN_KEYWORD_HYGIENE,
                            "add_negative_keywords_campaign",
                            str(local_id),
                            {"yandex_campaign_id": yid, "keywords": uniq},
                        ),
                    )
                )
            actions.extend(
                actions_for_keyword_hygiene(
                    campaign_local_id=str(local_id),
                    rows=rows,
                    ctr_low_threshold=float(cfg["ctr_low_threshold"]),
                    cost_threshold_rub=float(cfg["cost_threshold_rub"]),
                )
            )
    elif domain == DOMAIN_BID_OPTIMIZATION:
        for yid, (local_id, mode) in yandex_to_local.items():
            if mode != mode_filter:
                continue
            rows = [r for r in kw_rows if int(r.get("CampaignId") or 0) == yid]
            llm_summary = "bid_optimization rows:\n" + "\n".join(
                [f"id={r.get('Id')} bid={r.get('Bid')} ctr={r.get('Ctr')} cost={r.get('Cost')}" for r in rows[:80]]
            )
            llm_actions = generate_domain_actions(domain, llm_summary, db=db)
            llm_based_actions.extend(_llm_actions_to_agent_actions(domain, str(local_id), llm_actions))
            actions.extend(
                actions_for_bid_optimization(
                    campaign_local_id=str(local_id),
                    rows=rows,
                    ctr_high_threshold=float(cfg["ctr_high_threshold"]),
                    ctr_low_threshold=float(cfg["ctr_low_threshold"]),
                    bid_up_factor=float(cfg["bid_up_factor"]),
                )
            )
    elif domain in (DOMAIN_BUDGET_GUARD, DOMAIN_ANOMALY_WATCHDOG):
        for yid, (local_id, mode) in yandex_to_local.items():
            if mode != mode_filter:
                continue
            stats = tq.recent_campaign_stats(db, tenant.schema_name, local_id, limit=8)
            if not stats:
                continue
            latest = stats[0]
            baseline = stats[1] if len(stats) > 1 else latest
            if domain == DOMAIN_BUDGET_GUARD:
                llm_summary = (
                    f"budget_guard campaign={yid} stats="
                    + ", ".join([f"{s['date']}:cost={s['cost_rub']},clicks={s['clicks']}" for s in stats[:7]])
                )
                llm_actions = generate_domain_actions(domain, llm_summary, db=db)
                llm_based_actions.extend(_llm_actions_to_agent_actions(domain, str(local_id), llm_actions))
                spend_7d = sum(s["cost_rub"] for s in stats[:7])
                clicks_7d = sum(s["clicks"] for s in stats[:7])
                c = tq.get_campaign_by_id(db, tenant.schema_name, local_id)
                if c:
                    actions.extend(
                        actions_for_budget_guard(
                            campaign_local_id=str(local_id),
                            yandex_campaign_id=int(c["yandex_campaign_id"]),
                            name=str(c["name"]),
                            spend_7d=spend_7d,
                            clicks_7d=clicks_7d,
                            hard_weekly_limit_rub=float(domain_cfg["hard_weekly_limit_rub"]),
                        )
                    )
            else:
                watermark = tq.get_domain_watermark(db, tenant.schema_name, DOMAIN_ANOMALY_WATCHDOG)
                changes_meta = await yandex_direct.changes_check(
                    token, [yid], last_change_timestamp=watermark or None, client_login=client_login
                )
                ts = str(changes_meta.get("Timestamp") or "").strip()
                if ts:
                    tq.set_domain_watermark(db, tenant.schema_name, DOMAIN_ANOMALY_WATCHDOG, ts)
                llm_summary = (
                    f"anomaly_watchdog campaign={yid} latest={latest} baseline={baseline}. changes={changes_meta}"
                )
                llm_actions = generate_domain_actions(domain, llm_summary, db=db)
                llm_based_actions.extend(_llm_actions_to_agent_actions(domain, str(local_id), llm_actions))
                actions.extend(
                    actions_for_anomaly_watchdog(
                        campaign_local_id=str(local_id),
                        yandex_campaign_id=yid,
                        latest_cost=float(latest["cost_rub"]),
                        latest_clicks=int(latest["clicks"]),
                        baseline_cost=float(baseline["cost_rub"]),
                        baseline_clicks=int(baseline["clicks"]),
                    )
                )
    elif domain == DOMAIN_AD_ROTATION:
        for yid, (local_id, mode) in yandex_to_local.items():
            if mode != mode_filter:
                continue
            rows = await yandex_direct.ad_performance_rows(token, [yid], client_login=client_login)
            llm_summary = "ad_rotation rows:\n" + "\n".join(
                [f"id={r.get('Id')} state={r.get('State')} clicks={r.get('Clicks')} impr={r.get('Impressions')}" for r in rows[:80]]
            )
            llm_actions = generate_domain_actions(domain, llm_summary, db=db)
            llm_based_actions.extend(_llm_actions_to_agent_actions(domain, str(local_id), llm_actions))
            actions.extend(actions_for_ad_rotation(campaign_local_id=str(local_id), rows=rows))
    elif domain == DOMAIN_RETARGETING_TUNING:
        for yid, (local_id, mode) in yandex_to_local.items():
            if mode != mode_filter:
                continue
            rows = await yandex_direct.audience_targets_get(token, [yid], client_login=client_login)
            bidmods = await yandex_direct.bidmodifiers_get(token, [yid], client_login=client_login)
            retarget_lists = await yandex_direct.retargetinglists_get(token, client_login=client_login)
            llm_summary = "retargeting_tuning rows:\n" + "\n".join(
                [f"id={r.get('Id')} bid_modifier={r.get('BidModifier')} state={r.get('State')}" for r in rows[:80]]
            ) + (
                "\nbid_modifiers="
                + ", ".join([str(x.get("Type") or "") for x in bidmods[:30]])
                + "\nretarget_lists="
                + ", ".join([str(x.get("Name") or "") for x in retarget_lists[:30]])
            )
            llm_actions = generate_domain_actions(domain, llm_summary, db=db)
            llm_based_actions.extend(_llm_actions_to_agent_actions(domain, str(local_id), llm_actions))
            actions.extend(actions_for_retargeting_tuning(campaign_local_id=str(local_id), audience_targets=rows))
            # fallback rule from new source: if mobile modifier exists and is too conservative, raise to 110%
            for bm in bidmods:
                if not isinstance(bm, dict):
                    continue
                if str(bm.get("Type") or "") != "MOBILE_ADJUSTMENT":
                    continue
                madj = bm.get("MobileAdjustment")
                if not isinstance(madj, dict):
                    continue
                cur = int(madj.get("BidModifier") or 100)
                if cur < 105:
                    ok = await yandex_direct.bidmodifiers_update_mobile(token, yid, 110, client_login=client_login)
                    if ok:
                        tq.insert_agent_log(
                            db,
                            tenant.schema_name,
                            local_id,
                            "info",
                            "Fallback retargeting_tuning: повышена mobile корректировка ставки до 110%",
                            {"campaign_id": yid, "previous_mobile_bid_modifier": cur},
                        )
                    break

    # LLM is primary when valid; deterministic rules remain fallback.
    if llm_based_actions:
        converted = []
        for a in llm_based_actions:
            key = _stable_idempotency_key(a["domain"], a["action_type"], a["campaign_local_id"], a["payload_after"])
            converted.append(
                AgentAction(
                    domain=a["domain"],
                    action_type=a["action_type"],
                    campaign_local_id=a["campaign_local_id"],
                    payload_before=a["payload_before"],
                    payload_after=a["payload_after"],
                    idempotency_key=key,
                )
            )
        actions = converted

    # For advisor mode, store actionable recommendations and do not mutate Yandex.
    if mode_filter == "advisor":
        for action in actions[:max_changes]:
            title, body = _action_human_text(action)
            local_id = UUID(action.campaign_local_id) if action.campaign_local_id else None
            if not local_id:
                continue
            tq.insert_recommendation(
                db,
                tenant.schema_name,
                local_id,
                action.domain,
                title,
                body,
                _to_recommendation_payload(action),
                status="pending",
            )
            tq.insert_agent_log(
                db,
                tenant.schema_name,
                local_id,
                "info",
                f"Advisor/{action.domain}: создана рекомендация {action.action_type}",
                {"payload": action.payload_after},
            )
        return min(len(actions), max_changes)

    applied = 0
    for action in actions[:max_changes]:
        if await _apply_action(db, tenant, token, client_login, action, dry_run=dry_run):
            applied += 1
            # Autopilot keeps the recommendation trace with applied status.
            local_id = UUID(action.campaign_local_id) if action.campaign_local_id else None
            if local_id:
                title, body = _action_human_text(action)
                tq.insert_recommendation(
                    db,
                    tenant.schema_name,
                    local_id,
                    action.domain,
                    title,
                    body,
                    _to_recommendation_payload(action),
                    status="applied" if not dry_run else "pending",
                )
    # Lightweight post-check: after optimization domains, auto-rollback last action on severe KPI degradation.
    if not dry_run and applied and domain in {DOMAIN_BID_OPTIMIZATION, DOMAIN_KEYWORD_HYGIENE, DOMAIN_AD_ROTATION}:
        severe = False
        for local_id, mode in yandex_to_local.values():
            if mode != "autopilot":
                continue
            stats = tq.recent_campaign_stats(db, tenant.schema_name, local_id, limit=2)
            if len(stats) < 2:
                continue
            cur, prev = stats[0], stats[1]
            if float(prev["cost_rub"]) > 0 and float(cur["cost_rub"]) > float(prev["cost_rub"]) * 1.8 and float(
                cur["ctr"]
            ) < float(prev["ctr"]) * 0.5:
                severe = True
                break
        if severe:
            rows = tq.recent_action_history(db, tenant.schema_name, campaign_id=None, limit=1)
            if rows:
                last = rows[0]
                a_type = str(last["action_type"])
                before = last["payload_before"] or {}
                if a_type == "suspend_keyword":
                    kid = int(before.get("keyword_id") or 0)
                    if kid:
                        await yandex_direct.keywords_resume(token, [kid], client_login=client_login)
                elif a_type == "set_bid":
                    kid = int(before.get("keyword_id") or 0)
                    bid = float(before.get("bid_rub") or 0)
                    if kid and bid > 0:
                        await yandex_direct.keywords_set_bids(
                            token, [{"KeywordId": kid, "Bid": int(bid * 1_000_000)}], client_login=client_login
                        )
                elif a_type == "suspend_ad":
                    aid = int(before.get("ad_id") or 0)
                    if aid:
                        await yandex_direct.ads_resume(token, [aid], client_login=client_login)
                elif a_type == "add_negative_keywords_campaign":
                    # conservative rollback is skipped; campaign negatives are additive and should be manually reviewed
                    pass
                tq.insert_agent_log(
                    db,
                    tenant.schema_name,
                    None,
                    "warning",
                    "Auto-rollback: обнаружена деградация KPI после доменного прогона",
                    {"domain": domain, "rolled_back_action": a_type},
                )
                await send_alert(
                    "autopilot_auto_rollback",
                    {"tenant": tenant.name, "domain": domain, "rolled_back_action": a_type, "corr": get_correlation_id()},
                )
    if dry_run and applied:
        await send_alert(
            "domain_dry_run_preview",
            {"tenant": tenant.name, "domain": domain, "applied_preview": applied, "corr": get_correlation_id()},
        )
    return applied

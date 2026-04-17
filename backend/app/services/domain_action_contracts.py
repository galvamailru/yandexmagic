from __future__ import annotations

from typing import Any

ALLOWED_ACTIONS: dict[str, set[str]] = {
    "keyword_hygiene": {"suspend_keyword", "resume_keyword", "add_negative_keywords_campaign"},
    "bid_optimization": {"set_bid"},
    "budget_guard": {"suspend_campaign", "set_campaign_daily_budget"},
    "ad_rotation": {"suspend_ad", "resume_ad"},
    "retargeting_tuning": {"update_audience_bid_modifier"},
    "anomaly_watchdog": {"suspend_campaign"},
}


def contract_hint(domain: str) -> str:
    return (
        "Верни ТОЛЬКО JSON-массив actions. Каждый элемент: "
        "{action_type, reason, entity, params}. "
        "entity: keyword|ad|campaign|audience_target. "
        "params — только необходимые поля.\n"
        "Допустимые action_type для domain="
        f"{domain}: {sorted(ALLOWED_ACTIONS.get(domain, set()))}.\n"
        "Примеры params: "
        "set_bid -> {keyword_id, bid_rub}; "
        "suspend_keyword -> {keyword_id}; "
        "suspend_ad -> {ad_id}; "
        "suspend_campaign -> {yandex_campaign_id}; "
        "set_campaign_daily_budget -> {yandex_campaign_id, amount_rub}; "
        "update_audience_bid_modifier -> {audience_target_id, bid_modifier_percent}; "
        "add_negative_keywords_campaign -> {yandex_campaign_id, keywords:[...]}."
    )


def validate_domain_actions(domain: str, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    allowed = ALLOWED_ACTIONS.get(domain, set())
    for a in actions:
        if not isinstance(a, dict):
            continue
        action_type = str(a.get("action_type") or "").strip()
        if action_type not in allowed:
            continue
        params = a.get("params")
        if not isinstance(params, dict):
            continue
        cleaned = {
            "action_type": action_type,
            "reason": str(a.get("reason") or "")[:500],
            "entity": str(a.get("entity") or ""),
            "params": params,
        }
        if action_type == "set_bid":
            if int(params.get("keyword_id") or 0) <= 0:
                continue
            try:
                bid = float(params.get("bid_rub") or 0)
            except Exception:  # noqa: BLE001
                continue
            if bid <= 0:
                continue
            cleaned["params"] = {"keyword_id": int(params["keyword_id"]), "bid_rub": bid}
        elif action_type in {"suspend_keyword", "resume_keyword"}:
            if int(params.get("keyword_id") or 0) <= 0:
                continue
            cleaned["params"] = {"keyword_id": int(params["keyword_id"])}
        elif action_type in {"suspend_ad", "resume_ad"}:
            if int(params.get("ad_id") or 0) <= 0:
                continue
            cleaned["params"] = {"ad_id": int(params["ad_id"])}
        elif action_type == "suspend_campaign":
            if int(params.get("yandex_campaign_id") or 0) <= 0:
                continue
            cleaned["params"] = {"yandex_campaign_id": int(params["yandex_campaign_id"])}
        elif action_type == "set_campaign_daily_budget":
            if int(params.get("yandex_campaign_id") or 0) <= 0:
                continue
            try:
                amount = float(params.get("amount_rub") or 0)
            except Exception:  # noqa: BLE001
                continue
            if amount <= 0:
                continue
            cleaned["params"] = {"yandex_campaign_id": int(params["yandex_campaign_id"]), "amount_rub": amount}
        elif action_type == "add_negative_keywords_campaign":
            campaign_id = int(params.get("yandex_campaign_id") or 0)
            items = params.get("keywords")
            if campaign_id <= 0 or not isinstance(items, list):
                continue
            kws = [str(x).strip() for x in items if str(x).strip()]
            if not kws:
                continue
            cleaned["params"] = {"yandex_campaign_id": campaign_id, "keywords": kws[:50]}
        elif action_type == "update_audience_bid_modifier":
            atid = int(params.get("audience_target_id") or 0)
            mod = int(params.get("bid_modifier_percent") or 0)
            if atid <= 0 or mod <= 0:
                continue
            cleaned["params"] = {"audience_target_id": atid, "bid_modifier_percent": mod}
        out.append(cleaned)
    return out

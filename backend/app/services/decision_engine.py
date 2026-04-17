from __future__ import annotations

import hashlib
from typing import Any

from app.services.agent_domains import (
    AgentAction,
    DOMAIN_AD_ROTATION,
    DOMAIN_ANOMALY_WATCHDOG,
    DOMAIN_BID_OPTIMIZATION,
    DOMAIN_BUDGET_GUARD,
    DOMAIN_KEYWORD_HYGIENE,
    DOMAIN_RETARGETING_TUNING,
)


def _mk_key(domain: str, action_type: str, *parts: object) -> str:
    raw = "|".join([domain, action_type, *[str(x) for x in parts]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_action(
    *,
    domain: str,
    action_type: str,
    campaign_local_id: str | None,
    payload_before: dict[str, Any],
    payload_after: dict[str, Any],
    key_parts: list[object],
) -> AgentAction:
    return AgentAction(
        domain=domain,
        action_type=action_type,
        campaign_local_id=campaign_local_id,
        payload_before=payload_before,
        payload_after=payload_after,
        idempotency_key=_mk_key(domain, action_type, *key_parts),
    )


def actions_for_keyword_hygiene(
    *,
    campaign_local_id: str,
    rows: list[dict[str, Any]],
    ctr_low_threshold: float,
    cost_threshold_rub: float,
) -> list[AgentAction]:
    actions: list[AgentAction] = []
    for r in rows:
        kid = int(r.get("Id") or 0)
        if not kid:
            continue
        ctr = float(r.get("Ctr") or 0)
        cost = float(r.get("Cost") or 0)
        status = str(r.get("Status") or "")
        if ctr < ctr_low_threshold and cost >= cost_threshold_rub and status != "SUSPENDED":
            actions.append(
                _build_action(
                    domain=DOMAIN_KEYWORD_HYGIENE,
                    action_type="suspend_keyword",
                    campaign_local_id=campaign_local_id,
                    payload_before={"keyword_id": kid, "status": status},
                    payload_after={"keyword_id": kid, "status": "SUSPENDED"},
                    key_parts=[campaign_local_id, kid, "suspend"],
                )
            )
    return actions


def actions_for_bid_optimization(
    *,
    campaign_local_id: str,
    rows: list[dict[str, Any]],
    ctr_high_threshold: float,
    ctr_low_threshold: float,
    bid_up_factor: float,
) -> list[AgentAction]:
    actions: list[AgentAction] = []
    for r in rows:
        kid = int(r.get("Id") or 0)
        bid = float(r.get("Bid") or 0)
        ctr = float(r.get("Ctr") or 0)
        if not kid or bid <= 0:
            continue
        if ctr >= ctr_high_threshold:
            new_bid = round(bid * bid_up_factor, 2)
            actions.append(
                _build_action(
                    domain=DOMAIN_BID_OPTIMIZATION,
                    action_type="set_bid",
                    campaign_local_id=campaign_local_id,
                    payload_before={"keyword_id": kid, "bid_rub": bid},
                    payload_after={"keyword_id": kid, "bid_rub": new_bid},
                    key_parts=[campaign_local_id, kid, "up", int(new_bid * 100)],
                )
            )
        elif ctr > 0 and ctr <= max(0.1, ctr_low_threshold / 2):
            new_bid = round(max(0.3, bid * 0.9), 2)
            if new_bid < bid:
                actions.append(
                    _build_action(
                        domain=DOMAIN_BID_OPTIMIZATION,
                        action_type="set_bid",
                        campaign_local_id=campaign_local_id,
                        payload_before={"keyword_id": kid, "bid_rub": bid},
                        payload_after={"keyword_id": kid, "bid_rub": new_bid},
                        key_parts=[campaign_local_id, kid, "down", int(new_bid * 100)],
                    )
                )
    return actions


def actions_for_budget_guard(
    *,
    campaign_local_id: str,
    yandex_campaign_id: int,
    name: str,
    spend_7d: float,
    clicks_7d: int,
    hard_weekly_limit_rub: float,
) -> list[AgentAction]:
    if spend_7d < hard_weekly_limit_rub or hard_weekly_limit_rub <= 0:
        return []
    # Emergency: if there is spending but almost no clicks - pause campaign
    if spend_7d > hard_weekly_limit_rub and clicks_7d <= 1:
        return [
            _build_action(
                domain=DOMAIN_BUDGET_GUARD,
                action_type="suspend_campaign",
                campaign_local_id=campaign_local_id,
                payload_before={"yandex_campaign_id": yandex_campaign_id, "name": name, "state": "ON"},
                payload_after={"yandex_campaign_id": yandex_campaign_id, "name": name, "state": "SUSPENDED"},
                key_parts=[campaign_local_id, yandex_campaign_id, "budget_guard_suspend"],
            )
        ]
    return []


def actions_for_ad_rotation(
    *,
    campaign_local_id: str,
    rows: list[dict[str, Any]],
) -> list[AgentAction]:
    actions: list[AgentAction] = []
    for r in rows:
        aid = int(r.get("Id") or 0)
        clicks = int(r.get("Clicks") or 0)
        impr = int(r.get("Impressions") or 0)
        state = str(r.get("State") or "")
        if not aid:
            continue
        ctr = (clicks / impr) * 100 if impr else 0.0
        if impr >= 300 and ctr < 0.3 and state == "ON":
            actions.append(
                _build_action(
                    domain=DOMAIN_AD_ROTATION,
                    action_type="suspend_ad",
                    campaign_local_id=campaign_local_id,
                    payload_before={"ad_id": aid, "state": state},
                    payload_after={"ad_id": aid, "state": "SUSPENDED"},
                    key_parts=[campaign_local_id, aid, "suspend_ad"],
                )
            )
    return actions


def actions_for_anomaly_watchdog(
    *,
    campaign_local_id: str,
    yandex_campaign_id: int,
    latest_cost: float,
    latest_clicks: int,
    baseline_cost: float,
    baseline_clicks: int,
) -> list[AgentAction]:
    # Simple anomaly: cost spikes while clicks collapse.
    if baseline_cost <= 0:
        return []
    cost_spike = latest_cost >= baseline_cost * 2.0
    click_drop = baseline_clicks > 0 and latest_clicks <= max(1, int(baseline_clicks * 0.4))
    if not (cost_spike and click_drop):
        return []
    return [
        _build_action(
            domain=DOMAIN_ANOMALY_WATCHDOG,
            action_type="suspend_campaign",
            campaign_local_id=campaign_local_id,
            payload_before={"yandex_campaign_id": yandex_campaign_id, "state": "ON"},
            payload_after={"yandex_campaign_id": yandex_campaign_id, "state": "SUSPENDED"},
            key_parts=[campaign_local_id, yandex_campaign_id, "anomaly_suspend"],
        )
    ]


def actions_for_retargeting_tuning(
    *,
    campaign_local_id: str,
    audience_targets: list[dict[str, Any]],
) -> list[AgentAction]:
    # Placeholder deterministic policy: increase adjustment for high-performing audience segments.
    actions: list[AgentAction] = []
    for row in audience_targets:
        target_id = int(row.get("Id") or 0)
        bid_adj = int(row.get("BidModifier") or 100)
        conversions = int(row.get("Conversions") or 0)
        if target_id and conversions >= 3 and bid_adj < 130:
            new_val = min(130, bid_adj + 10)
            actions.append(
                _build_action(
                    domain=DOMAIN_RETARGETING_TUNING,
                    action_type="update_audience_bid_modifier",
                    campaign_local_id=campaign_local_id,
                    payload_before={"audience_target_id": target_id, "bid_modifier_percent": bid_adj},
                    payload_after={"audience_target_id": target_id, "bid_modifier_percent": new_val},
                    key_parts=[campaign_local_id, target_id, new_val],
                )
            )
    return actions

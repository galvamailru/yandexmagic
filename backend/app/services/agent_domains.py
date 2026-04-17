from __future__ import annotations

from dataclasses import dataclass

DOMAIN_ANOMALY_WATCHDOG = "anomaly_watchdog"
DOMAIN_BUDGET_GUARD = "budget_guard"
DOMAIN_BID_OPTIMIZATION = "bid_optimization"
DOMAIN_KEYWORD_HYGIENE = "keyword_hygiene"
DOMAIN_AD_ROTATION = "ad_rotation"
DOMAIN_RETARGETING_TUNING = "retargeting_tuning"

ALL_ACTION_DOMAINS = [
    DOMAIN_ANOMALY_WATCHDOG,
    DOMAIN_BUDGET_GUARD,
    DOMAIN_BID_OPTIMIZATION,
    DOMAIN_KEYWORD_HYGIENE,
    DOMAIN_AD_ROTATION,
    DOMAIN_RETARGETING_TUNING,
]

# protective first, then optimization
DOMAIN_PRIORITY = [
    DOMAIN_ANOMALY_WATCHDOG,
    DOMAIN_BUDGET_GUARD,
    DOMAIN_BID_OPTIMIZATION,
    DOMAIN_KEYWORD_HYGIENE,
    DOMAIN_AD_ROTATION,
    DOMAIN_RETARGETING_TUNING,
]


@dataclass(frozen=True)
class AgentAction:
    domain: str
    action_type: str
    campaign_local_id: str | None
    payload_before: dict
    payload_after: dict
    idempotency_key: str

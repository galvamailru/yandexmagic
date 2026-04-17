from sqlalchemy import text
from sqlalchemy.orm import Session


def create_tenant_schema(db: Session, schema_name: str) -> None:
    safe = _validate_schema_name(schema_name)
    stmts = [
        f'CREATE SCHEMA IF NOT EXISTS "{safe}"',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".campaigns (
    id UUID PRIMARY KEY,
    yandex_campaign_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'UNKNOWN',
    mode TEXT NOT NULL DEFAULT 'monitoring',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".daily_stats (
    id UUID PRIMARY KEY,
    campaign_id UUID NOT NULL REFERENCES "{safe}".campaigns(id) ON DELETE CASCADE,
    stat_date DATE NOT NULL,
    cost_rub NUMERIC(18,4) NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    impressions BIGINT NOT NULL DEFAULT 0,
    ctr NUMERIC(10,6) NOT NULL DEFAULT 0,
    avg_cpc_rub NUMERIC(18,4),
    UNIQUE (campaign_id, stat_date)
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".recommendations (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES "{safe}".campaigns(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{{}}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".agent_logs (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES "{safe}".campaigns(id) ON DELETE SET NULL,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{{}}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".keywords_snapshot (
    id UUID PRIMARY KEY,
    campaign_id UUID NOT NULL REFERENCES "{safe}".campaigns(id) ON DELETE CASCADE,
    keyword_id BIGINT NOT NULL,
    keyword_text TEXT NOT NULL,
    bid_rub NUMERIC(18,4),
    status TEXT NOT NULL DEFAULT 'ON',
    ctr NUMERIC(10,6),
    cost_rub NUMERIC(18,4) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (campaign_id, keyword_id)
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".agent_settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    ctr_low_threshold NUMERIC(10,6) NOT NULL DEFAULT 1.0,
    ctr_high_threshold NUMERIC(10,6) NOT NULL DEFAULT 5.0,
    cost_threshold_rub NUMERIC(18,4) NOT NULL DEFAULT 500.0,
    bid_up_factor NUMERIC(10,6) NOT NULL DEFAULT 1.10,
    autopilot_dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    max_changes_per_cycle INTEGER NOT NULL DEFAULT 30,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".action_history (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES "{safe}".campaigns(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    payload_before TEXT NOT NULL DEFAULT '{{}}',
    payload_after TEXT NOT NULL DEFAULT '{{}}',
    correlation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".domain_settings (
    domain TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    max_changes_per_run INTEGER NOT NULL DEFAULT 10,
    hard_weekly_limit_rub NUMERIC(18,4) NOT NULL DEFAULT 0,
    schedule_hint TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
        f'''
CREATE TABLE IF NOT EXISTS "{safe}".idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)''',
    ]
    for sql in stmts:
        db.execute(text(sql))
    db.execute(
        text(
            f'''
INSERT INTO "{safe}".agent_settings
(id, ctr_low_threshold, ctr_high_threshold, cost_threshold_rub, bid_up_factor, autopilot_dry_run, max_changes_per_cycle)
VALUES (1, 1.0, 5.0, 500.0, 1.10, TRUE, 30)
ON CONFLICT (id) DO NOTHING
'''
        )
    )
    domain_defaults = [
        ("anomaly_watchdog", True, 8, 0.0, "*/3h"),
        ("budget_guard", True, 8, 7000.0, "*/4h"),
        ("bid_optimization", True, 15, 0.0, "daily"),
        ("keyword_hygiene", True, 15, 0.0, "daily"),
        ("ad_rotation", True, 10, 0.0, "3x_week"),
        ("retargeting_tuning", True, 10, 0.0, "weekly"),
    ]
    for d, enabled, max_changes, limit_rub, schedule_hint in domain_defaults:
        db.execute(
            text(
                f'''
INSERT INTO "{safe}".domain_settings(domain, enabled, max_changes_per_run, hard_weekly_limit_rub, schedule_hint, updated_at)
VALUES (:d, :en, :m, :lim, :s, NOW())
ON CONFLICT (domain) DO NOTHING
'''
            ),
            {"d": d, "en": enabled, "m": max_changes, "lim": limit_rub, "s": schedule_hint},
        )
    db.commit()


def _validate_schema_name(schema_name: str) -> str:
    if not schema_name.startswith("tenant_"):
        raise ValueError("Invalid tenant schema name")
    for ch in schema_name:
        if ch not in "abcdefghijklmnopqrstuvwxyz0123456789_":
            raise ValueError("Invalid tenant schema name")
    return schema_name

from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.models import public as models_public
from app.services.tenant_schema import create_tenant_schema


def init_public_schema() -> None:
    Base.metadata.create_all(bind=engine, tables=[
        models_public.User.__table__,
        models_public.Tenant.__table__,
        models_public.TenantMembership.__table__,
        models_public.TenantYandexToken.__table__,
    ])
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
CREATE TABLE IF NOT EXISTS wizard_sessions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    step INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
            )
        )
        db.execute(
            text(
                """
ALTER TABLE tenant_yandex_tokens
ADD COLUMN IF NOT EXISTS client_login TEXT
"""
            )
        )
        db.execute(
            text(
                """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
            )
        )
        db.execute(
            text(
                """
CREATE TABLE IF NOT EXISTS job_locks (
    name TEXT PRIMARY KEY,
    locked_until TIMESTAMPTZ NOT NULL
);
"""
            )
        )
        db.execute(
            text(
                """
CREATE TABLE IF NOT EXISTS job_runs (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms BIGINT,
    details TEXT NOT NULL DEFAULT '{}'
);
"""
            )
        )
        db.execute(
            text(
                """
INSERT INTO app_settings(key, value)
VALUES ('ai_agent_prompt', :value)
ON CONFLICT (key) DO NOTHING
"""
            ),
            {
                "value": (
                    "Ты senior PPC-специалист по Яндекс Директ. Анализируй статистику строго по данным, "
                    "не придумывай факты. Отвечай на русском. Возвращай ТОЛЬКО JSON-массив объектов "
                    "{kind,title,body,payload}, без markdown и без пояснений вне JSON. "
                    "Допустимые kind: general, keyword, ad, bid, budget. "
                    "Payload contract: payload всегда объект. "
                    "Для kind=keyword обязательны payload.action (suspend|resume|bid_up|bid_down|none) "
                    "и payload.keyword_id (число или null). "
                    "Для kind=ad обязательны payload.action (pause_ad|resume_ad|none) и payload.ad_id (число или null). "
                    "Для kind=bid обязательны payload.action (bid_up|bid_down|none), payload.keyword_id (число или null), "
                    "payload.percent (число 0..100 или null). "
                    "Для kind=budget обязательны payload.action (budget_up|budget_down|none), payload.amount (число или null), "
                    "payload.period (daily|weekly|monthly|null). "
                    "Для kind=general используй payload.action=none и payload.note (строка). "
                    "Если данных недостаточно, все равно верни массив с одним объектом kind=general,title='Анализ', "
                    "body с кратким выводом и payload={action:'none',note:'недостаточно данных'}. "
                    "Для плохих фраз при CTR<1% и расходе>500 предлагай suspend. "
                    "Для эффективных при CTR>5% предлагай bid_up с аккуратным шагом."
                )
            },
        )
        # Ensure tenant schemas are upgraded with latest tables.
        tenants = db.query(models_public.Tenant).all()
        for t in tenants:
            create_tenant_schema(db, t.schema_name)
        db.commit()
    finally:
        db.close()

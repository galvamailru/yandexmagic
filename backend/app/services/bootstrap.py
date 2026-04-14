from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.models import public as models_public


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
INSERT INTO app_settings(key, value)
VALUES ('ai_agent_prompt', :value)
ON CONFLICT (key) DO NOTHING
"""
            ),
            {
                "value": (
                    "Ты senior PPC-специалист по Яндекс Директ. Анализируй статистику строго по данным, "
                    "не придумывай факты. Отвечай на русском. Если просят рекомендации — возвращай JSON-массив "
                    "объектов {kind,title,body,payload}. Для плохих фраз при CTR<1% и расходе>500 предлагай "
                    "suspend. Для эффективных при CTR>5% предлагай bid_up с аккуратным шагом."
                )
            },
        )
        db.commit()
    finally:
        db.close()

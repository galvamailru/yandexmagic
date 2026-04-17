from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.models import public as models_public
from app.services.prompt_store import DEFAULT_DOMAIN_PROMPTS
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
CREATE TABLE IF NOT EXISTS domain_prompts (
    domain TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
            )
        )
        for domain, prompt in DEFAULT_DOMAIN_PROMPTS.items():
            db.execute(
                text(
                    """
INSERT INTO domain_prompts(domain, prompt, updated_at)
VALUES (:d, :p, NOW())
ON CONFLICT (domain) DO NOTHING
"""
                ),
                {"d": domain, "p": prompt},
            )
        # Ensure tenant schemas are upgraded with latest tables.
        tenants = db.query(models_public.Tenant).all()
        for t in tenants:
            create_tenant_schema(db, t.schema_name)
        db.commit()
    finally:
        db.close()

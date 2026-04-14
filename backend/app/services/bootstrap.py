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
        db.commit()
    finally:
        db.close()

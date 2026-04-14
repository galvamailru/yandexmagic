from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt_tokens import create_access_token
from app.database import get_db
from app.deps import require_platform_admin
from app.models.public import Tenant, User
from app.repositories import tenant_queries as tq
from app.schemas.common import AdminTenantOut, AgentLogOut, TokenResponse
from app.services.prompt_store import get_ai_prompt, set_ai_prompt

router = APIRouter(prefix="/admin", tags=["admin"])


class PromptBody(BaseModel):
    prompt: str


@router.get("/tenants", response_model=list[AdminTenantOut])
def list_tenants(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
) -> list[AdminTenantOut]:
    rows = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [
        AdminTenantOut(
            id=t.id,
            name=t.name,
            schema_name=t.schema_name,
            is_blocked=t.is_blocked,
            created_at=t.created_at,
        )
        for t in rows
    ]


@router.post("/tenants/{tenant_id}/block")
def block_tenant(
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
    blocked: bool = True,
) -> AdminTenantOut:
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    t.is_blocked = blocked
    db.add(t)
    db.commit()
    db.refresh(t)
    return AdminTenantOut(
        id=t.id,
        name=t.name,
        schema_name=t.schema_name,
        is_blocked=t.is_blocked,
        created_at=t.created_at,
    )


@router.post("/switch-tenant", response_model=TokenResponse)
def admin_switch_tenant(
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_platform_admin)],
) -> TokenResponse:
    t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    jwt = create_access_token(
        user_id=user.id,
        tenant_id=tenant_id,
        is_platform_admin=True,
        act_as_tenant_id=tenant_id,
    )
    return TokenResponse(access_token=jwt)


@router.get("/agent-logs", response_model=list[AgentLogOut])
def all_agent_logs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
    tenant_id: UUID | None = None,
    limit: int = 200,
) -> list[AgentLogOut]:
    if tenant_id:
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        rows = tq.list_agent_logs(db, t.schema_name, None, limit=limit)
    else:
        rows = []
        for t in db.query(Tenant).order_by(Tenant.created_at.desc()).limit(50).all():
            rows.extend(tq.list_agent_logs(db, t.schema_name, None, limit=50))
        rows = rows[:limit]
    return [
        AgentLogOut(
            id=UUID(r["id"]),
            campaign_id=UUID(r["campaign_id"]) if r.get("campaign_id") else None,
            level=r["level"],
            message=r["message"],
            details=r["details"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/ai-prompt")
def read_ai_prompt(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
) -> dict[str, str]:
    return {"prompt": get_ai_prompt(db)}


@router.put("/ai-prompt")
def update_ai_prompt(
    body: PromptBody,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
) -> dict[str, str]:
    text = body.prompt.strip()
    if len(text) < 20:
        raise HTTPException(status_code=400, detail="Prompt is too short")
    set_ai_prompt(db, text)
    return {"status": "ok"}

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.jwt_tokens import create_access_token
from app.database import get_db
from app.deps import require_platform_admin
from app.models.public import Tenant, TenantMembership, User
from app.repositories import tenant_queries as tq
from app.schemas.common import AdminTenantOut, AgentLogOut, TokenResponse
from app.services.prompt_store import get_ai_prompt, set_ai_prompt

router = APIRouter(prefix="/admin", tags=["admin"])


class PromptBody(BaseModel):
    prompt: str


class MembershipRoleBody(BaseModel):
    user_id: UUID
    role: str


@router.get("/tenants")
def list_tenants(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
    page: int = 1,
    limit: int = 20,
) -> dict:
    p = max(1, page)
    lim = min(max(1, limit), 100)
    total = db.query(Tenant).count()
    rows = db.query(Tenant).order_by(Tenant.created_at.desc()).offset((p - 1) * lim).limit(lim).all()
    items = [
        AdminTenantOut(
            id=t.id,
            name=t.name,
            schema_name=t.schema_name,
            is_blocked=t.is_blocked,
            created_at=t.created_at,
        )
        for t in rows
    ]
    return {"items": [x.model_dump() for x in items], "total": total, "page": p, "limit": lim}


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


@router.get("/agent-logs")
def all_agent_logs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
    tenant_id: UUID | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    p = max(1, page)
    lim = min(max(1, limit), 100)
    offset = (p - 1) * lim
    if tenant_id:
        t = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        rows, total = tq.list_agent_logs_paged(db, t.schema_name, None, limit=lim, offset=offset)
    else:
        rows = []
        total = 0
        for t in db.query(Tenant).order_by(Tenant.created_at.desc()).limit(50).all():
            chunk, chunk_total = tq.list_agent_logs_paged(db, t.schema_name, None, limit=lim, offset=0)
            rows.extend(chunk)
            total += chunk_total
        rows = sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)[offset : offset + lim]
    items = [
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
    return {"items": [x.model_dump() for x in items], "total": total, "page": p, "limit": lim}


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


@router.get("/job-runs")
def job_runs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
    page: int = 1,
    limit: int = 50,
) -> dict:
    p = max(1, page)
    lim = min(max(1, limit), 100)
    offset = (p - 1) * lim
    total = db.execute(text("SELECT COUNT(*) FROM job_runs")).scalar() or 0
    rows = db.execute(
        text(
            """
SELECT id, name, status, started_at, finished_at, duration_ms, details
FROM job_runs
ORDER BY started_at DESC
LIMIT :lim OFFSET :off
"""
        ),
        {"lim": lim, "off": offset},
    ).fetchall()
    import json

    items = [
        {
            "id": str(r[0]),
            "name": r[1],
            "status": r[2],
            "started_at": r[3].isoformat() if r[3] else None,
            "finished_at": r[4].isoformat() if r[4] else None,
            "duration_ms": r[5],
            "details": json.loads(r[6] or "{}"),
        }
        for r in rows
    ]
    return {"items": items, "total": int(total), "page": p, "limit": lim}


@router.post("/tenants/{tenant_id}/membership-role")
def set_membership_role(
    tenant_id: UUID,
    body: MembershipRoleBody,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_platform_admin)],
) -> dict[str, str]:
    if body.role not in {"owner", "manager", "viewer"}:
        raise HTTPException(status_code=400, detail="Role must be owner/manager/viewer")
    m = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == body.user_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Membership not found")
    m.role = body.role
    db.add(m)
    db.commit()
    return {"status": "ok"}

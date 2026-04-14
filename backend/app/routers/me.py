from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt_tokens import create_access_token
from app.database import get_db
from app.deps import get_current_user
from app.models.public import Tenant, TenantMembership, User
from app.schemas.common import AutopilotRiskBody, SwitchTenantBody, TenantBrief, TokenResponse, UserOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    return UserOut(
        id=user.id,
        login=user.login,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        autopilot_risk_accepted_at=user.autopilot_risk_accepted_at,
    )


@router.get("/tenants", response_model=list[TenantBrief])
def list_my_tenants(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[TenantBrief]:
    q = (
        db.query(Tenant)
        .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
        .filter(TenantMembership.user_id == user.id)
    )
    return [TenantBrief(id=t.id, name=t.name, schema_name=t.schema_name) for t in q.all()]


@router.post("/switch-tenant", response_model=TokenResponse)
def switch_tenant(
    body: SwitchTenantBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TokenResponse:
    m = (
        db.query(TenantMembership)
        .filter(TenantMembership.user_id == user.id, TenantMembership.tenant_id == body.tenant_id)
        .first()
    )
    if not m and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Not a member")
    if not db.query(Tenant).filter(Tenant.id == body.tenant_id).first():
        raise HTTPException(status_code=404, detail="Tenant not found")
    jwt = create_access_token(
        user_id=user.id,
        tenant_id=body.tenant_id,
        is_platform_admin=user.is_platform_admin,
        act_as_tenant_id=body.tenant_id if user.is_platform_admin else None,
    )
    return TokenResponse(access_token=jwt)


@router.post("/autopilot-risk", response_model=UserOut)
def accept_autopilot_risk(
    body: AutopilotRiskBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    if body.accept:
        user.autopilot_risk_accepted_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        db.refresh(user)
    return UserOut(
        id=user.id,
        login=user.login,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        autopilot_risk_accepted_at=user.autopilot_risk_accepted_at,
    )

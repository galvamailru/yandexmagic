from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt_tokens import decode_token
from app.database import get_db
from app.models.public import Tenant, TenantMembership, User


def _bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(_bearer_token)],
) -> User:
    try:
        payload = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == UUID(sub)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_effective_tenant_id(
    user: Annotated[User, Depends(get_current_user)],
    token: Annotated[str, Depends(_bearer_token)],
) -> UUID:
    try:
        payload = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    act = payload.get("act")
    tid = payload.get("tenant_id")
    if user.is_platform_admin and act:
        return UUID(act)
    if not tid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tenant selected")
    return UUID(tid)


def require_tenant_access(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[UUID, Depends(get_effective_tenant_id)],
) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.is_blocked and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Tenant blocked")
    if not user.is_platform_admin:
        m = (
            db.query(TenantMembership)
            .filter(TenantMembership.user_id == user.id, TenantMembership.tenant_id == tenant_id)
            .first()
        )
        if not m:
            raise HTTPException(status_code=403, detail="Forbidden")
    return tenant


def require_platform_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

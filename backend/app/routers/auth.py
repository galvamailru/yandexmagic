import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt_tokens import create_access_token
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models.public import Tenant, TenantMembership, TenantYandexToken, User
from app.schemas.common import OAuthCallbackBody, TokenResponse, YandexAuthUrl
from app.services import tenant_schema
from app.services import yandex_oauth

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _oauth_configured() -> bool:
    value = (settings.YANDEX_CLIENT_ID or "").strip()
    if not value:
        return False
    placeholders = {
        "replace_with_yandex_client_id",
        "your_yandex_client_id",
        "YANDEX_CLIENT_ID",
    }
    if value in placeholders or value.lower().startswith("replace_"):
        return False
    return True


@router.get("/yandex/url", response_model=YandexAuthUrl)
async def yandex_auth_url() -> YandexAuthUrl:
    if not _oauth_configured():
        raise HTTPException(status_code=500, detail="YANDEX_CLIENT_ID is not configured")
    state = secrets.token_urlsafe(16)
    return YandexAuthUrl(url=yandex_oauth.build_authorize_url(state), state=state)


@router.post("/yandex/callback", response_model=TokenResponse)
async def yandex_callback(body: OAuthCallbackBody, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    try:
        token_data = await yandex_oauth.exchange_code(body.code)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"OAuth failed: {exc}") from exc

    access = token_data.get("access_token")
    if not access:
        raise HTTPException(status_code=400, detail="No access_token in response")

    info = await yandex_oauth.fetch_yandex_login_info(access)
    yandex_id = str(info.get("id") or info.get("client_id") or "")
    if not yandex_id:
        raise HTTPException(status_code=400, detail="Cannot read Yandex user id")

    login = str(info.get("login") or "")
    email = info.get("default_email")
    display = info.get("display_name") or login

    user = db.query(User).filter(User.yandex_id == yandex_id).first()
    if not user:
        admin_ids = settings.platform_admin_id_set
        is_admin = yandex_id in admin_ids if admin_ids else False
        if not admin_ids:
            cnt = db.query(User).count()
            is_admin = cnt == 0
        user = User(
            yandex_id=yandex_id,
            login=login,
            email=email,
            display_name=display,
            is_platform_admin=is_admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    membership = db.query(TenantMembership).filter(TenantMembership.user_id == user.id).first()
    if not membership:
        schema_name = f"tenant_{user.id.hex}"
        tenant = Tenant(name=display or login or "Компания", schema_name=schema_name)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        tenant_schema.create_tenant_schema(db, schema_name)
        db.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner"))
        tok = TenantYandexToken(
            tenant_id=tenant.id,
            access_token=access,
            refresh_token=token_data.get("refresh_token"),
            expires_at=_expires_at(token_data.get("expires_in")),
        )
        db.add(tok)
        db.commit()
        tenant_id = tenant.id
    else:
        tenant_id = membership.tenant_id
        tok = db.query(TenantYandexToken).filter(TenantYandexToken.tenant_id == tenant_id).first()
        if tok:
            tok.access_token = access
            tok.refresh_token = token_data.get("refresh_token") or tok.refresh_token
            tok.expires_at = _expires_at(token_data.get("expires_in"))
        else:
            db.add(
                TenantYandexToken(
                    tenant_id=tenant_id,
                    access_token=access,
                    refresh_token=token_data.get("refresh_token"),
                    expires_at=_expires_at(token_data.get("expires_in")),
                )
            )
        db.commit()

    jwt = create_access_token(
        user_id=user.id,
        tenant_id=tenant_id,
        is_platform_admin=user.is_platform_admin,
        act_as_tenant_id=None,
    )
    return TokenResponse(access_token=jwt)


def _expires_at(expires_in: object) -> datetime | None:
    if not expires_in:
        return None
    try:
        sec = int(expires_in)
    except (TypeError, ValueError):
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=sec)


@router.post("/dev-token", response_model=TokenResponse, include_in_schema=False)
def dev_token(db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    """Local-only helper when OAuth is not configured."""
    if _oauth_configured():
        raise HTTPException(status_code=404, detail="OAuth is configured, dev-token is disabled")
    user = db.query(User).first()
    if not user:
        user = User(yandex_id="dev", login="dev", is_platform_admin=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    tenant = db.query(Tenant).first()
    if not tenant:
        schema_name = f"tenant_{user.id.hex}"
        tenant = Tenant(name="Dev tenant", schema_name=schema_name)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        tenant_schema.create_tenant_schema(db, schema_name)
        db.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner"))
        db.add(
            TenantYandexToken(
                tenant_id=tenant.id,
                access_token="mock",
            )
        )
        db.commit()
    jwt = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        is_platform_admin=user.is_platform_admin,
    )
    return TokenResponse(access_token=jwt)

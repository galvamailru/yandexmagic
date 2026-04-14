import urllib.parse
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

YANDEX_AUTH = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN = settings.YANDEX_OAUTH_TOKEN_URL
YANDEX_LOGIN_INFO = "https://login.yandex.ru/info"


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.YANDEX_CLIENT_ID,
        "redirect_uri": settings.YANDEX_REDIRECT_URI,
        "scope": "direct:api",
        "state": state,
    }
    return f"{YANDEX_AUTH}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.YANDEX_CLIENT_ID,
        "client_secret": settings.YANDEX_CLIENT_SECRET,
        "redirect_uri": settings.YANDEX_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            YANDEX_TOKEN,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_yandex_login_info(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(YANDEX_LOGIN_INFO, headers={"Authorization": f"OAuth {access_token}"})
        r.raise_for_status()
        return r.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.YANDEX_CLIENT_ID,
        "client_secret": settings.YANDEX_CLIENT_SECRET,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            YANDEX_TOKEN,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()

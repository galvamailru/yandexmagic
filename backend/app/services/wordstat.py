"""Yandex Wordstat topRequests — simplified."""

from typing import Any
import asyncio

import httpx

from app.config import get_settings

settings = get_settings()


async def top_requests(phrases: list[str], region: int = 225, access_token: str | None = None) -> list[dict[str, Any]]:
    if settings.YANDEX_MOCK:
        return [{"phrase": p, "shows": 10000 - i * 100, "top": 3} for i, p in enumerate(phrases[:20])]
    if not access_token:
        return [{"phrase": p, "shows": 0, "top": 0} for p in phrases]
    body = {"phrases": phrases[:40], "region": region}
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    delays = [0.4, 1.0, 2.0]
    for i, d in enumerate(delays):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(settings.WORDSTAT_URL, headers=headers, json=body)
                if r.status_code in (429, 500, 502, 503, 504) and i < len(delays) - 1:
                    await asyncio.sleep(d)
                    continue
                if r.status_code >= 400:
                    return [{"phrase": p, "shows": 0, "top": 0} for p in phrases]
                data = r.json()
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    return [x for x in data["items"] if isinstance(x, dict)]
                return [{"phrase": p, "shows": 0, "top": 0} for p in phrases]
        except Exception:  # noqa: BLE001
            if i < len(delays) - 1:
                await asyncio.sleep(d)
                continue
            return [{"phrase": p, "shows": 0, "top": 0} for p in phrases]
    return [{"phrase": p, "shows": 0, "top": 0} for p in phrases]

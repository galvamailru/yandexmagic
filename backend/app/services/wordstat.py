"""Yandex Wordstat topRequests — simplified."""

from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


async def top_requests(phrases: list[str], region: int = 225) -> list[dict[str, Any]]:
    if settings.YANDEX_MOCK:
        return [{"phrase": p, "shows": 10000 - i * 100, "top": 3} for i, p in enumerate(phrases[:20])]
    # Production: use official Wordstat API with OAuth; placeholder returns input echo.
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Real endpoint differs; keep safe fallback for MVP scaffolding.
        return [{"phrase": p, "shows": 0, "top": 0} for p in phrases]

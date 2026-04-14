from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


async def send_alert(event: str, payload: dict[str, Any]) -> None:
    if not settings.ALERT_WEBHOOK_URL:
        return
    body = {"event": event, "payload": payload}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(settings.ALERT_WEBHOOK_URL, json=body)
    except Exception:  # noqa: BLE001
        return

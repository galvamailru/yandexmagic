"""
Yandex Direct API v5 JSON client (Campaigns, Reports). Mock mode for local dev.
Docs: https://yandex.ru/dev/direct/doc/
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
import asyncio

import httpx

from app.config import get_settings

settings = get_settings()

API = "https://api.direct.yandex.com/json/v5/"


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }


async def _post_with_retry(url: str, token: str, body: dict[str, Any], timeout: float = 60.0) -> httpx.Response | None:
    delays = [0.4, 1.0, 2.0]
    for i, delay in enumerate(delays):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, headers=_headers(token), json=body)
                if r.status_code in (429, 500, 502, 503, 504):
                    if i < len(delays) - 1:
                        await asyncio.sleep(delay)
                        continue
                return r
        except Exception:  # noqa: BLE001
            if i < len(delays) - 1:
                await asyncio.sleep(delay)
                continue
            return None
    return None


async def campaigns_get(token: str) -> list[dict[str, Any]]:
    rows, _meta = await campaigns_get_with_meta(token)
    return rows


async def campaigns_get_with_meta(token: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if settings.YANDEX_MOCK:
        rows = [
            {"Id": 1001, "Name": "Демо: поиск", "State": "ON", "Status": "ACCEPTED"},
            {"Id": 1002, "Name": "Демо: РСЯ", "State": "SUSPENDED", "Status": "ACCEPTED"},
        ]
        return rows, {"source": "mock", "http_status": 200, "count": len(rows)}
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "State", "Status", "DailyBudget"],
        },
    }
    r = await _post_with_retry(f"{API}campaigns", token, body)
    if not r:
        return [], {"source": "api", "http_status": None, "count": 0, "error": "network_or_timeout"}
    if r.status_code >= 400:
        err: str | None = None
        try:
            payload = r.json()
            err = json.dumps(payload, ensure_ascii=False)[:400]
        except Exception:  # noqa: BLE001
            err = (r.text or "")[:400]
        return [], {"source": "api", "http_status": r.status_code, "count": 0, "error": err}
    data = r.json()
    rows = data.get("result", {}).get("Campaigns", []) or []
    return rows, {"source": "api", "http_status": r.status_code, "count": len(rows)}


async def reports_campaign_daily(token: str, campaign_ids: list[int], day_from: date, day_to: date) -> list[dict[str, Any]]:
    """Return rows with CampaignId, Date, Cost, Clicks, Impressions."""
    if settings.YANDEX_MOCK:
        out: list[dict[str, Any]] = []
        d = day_from
        while d <= day_to:
            for cid in campaign_ids:
                out.append(
                    {
                        "CampaignId": cid,
                        "Date": d.isoformat(),
                        "Cost": float(1200 + (cid % 7) * 100),
                        "Clicks": 40 + cid % 10,
                        "Impressions": 4000,
                    }
                )
            d += timedelta(days=1)
        return out

    body = {
        "params": {
            "SelectionCriteria": {"Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(x) for x in campaign_ids]}]},
            "FieldNames": ["CampaignId", "Date", "Cost", "Clicks", "Impressions"],
            "ReportName": f"ymagic_{day_from}_{day_to}",
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",
            "IncludeDiscount": "NO",
        }
    }
    # Reports API is two-step: create report then download — simplified mock path for real impl would use offline report queue.
    # MVP: use keywordless aggregate via simplified placeholder — return empty to avoid blocking.
    r = await _post_with_retry(f"{API}reports", token, body, timeout=120.0)
    if not r or r.status_code >= 400:
        return []
    return []


async def keyword_performance_rows(
    token: str, campaign_ids: list[int]
) -> list[dict[str, Any]]:
    """Keyword-level stats for autopilot rules (mock fills CTR/cost)."""
    if settings.YANDEX_MOCK:
        rows = []
        for cid in campaign_ids:
            rows.extend(
                [
                    {
                        "CampaignId": cid,
                        "Id": cid * 1000 + 1,
                        "Keyword": "купить товар",
                        "Bid": 15.0,
                        "UserParam1": "ON",
                        "Cost": 600.0,
                        "Ctr": 0.8,
                    },
                    {
                        "CampaignId": cid,
                        "Id": cid * 1000 + 2,
                        "Keyword": "доставка",
                        "Bid": 20.0,
                        "UserParam1": "ON",
                        "Cost": 120.0,
                        "Ctr": 6.5,
                    },
                ]
            )
        return rows
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "Keyword", "CampaignId", "Bid", "Status", "Statistics"],
        },
    }
    r = await _post_with_retry(f"{API}keywords", token, body)
    if not r or r.status_code >= 400:
        return []
    return r.json().get("result", {}).get("Keywords", []) or []


async def keywords_suspend(token: str, keyword_ids: list[int]) -> bool:
    if settings.YANDEX_MOCK or not keyword_ids:
        return True
    body = {
        "method": "suspend",
        "params": {
            "SelectionCriteria": {"Ids": keyword_ids},
        },
    }
    r = await _post_with_retry(f"{API}keywords", token, body)
    return bool(r and r.status_code < 400)


async def keywords_resume(token: str, keyword_ids: list[int]) -> bool:
    if settings.YANDEX_MOCK or not keyword_ids:
        return True
    body = {
        "method": "resume",
        "params": {"SelectionCriteria": {"Ids": keyword_ids}},
    }
    r = await _post_with_retry(f"{API}keywords", token, body)
    return bool(r and r.status_code < 400)


async def keywords_set_bids(token: str, items: list[dict[str, Any]]) -> bool:
    if settings.YANDEX_MOCK or not items:
        return True
    body = {"method": "setBids", "params": {"Bids": items}}
    r = await _post_with_retry(f"{API}keywords", token, body)
    return bool(r and r.status_code < 400)


async def campaigns_add(token: str, campaign_spec: dict[str, Any]) -> int | None:
    if settings.YANDEX_MOCK:
        return 9000 + int(json.dumps(campaign_spec, sort_keys=True)[:4].encode().hex()[:4], 16) % 10000
    body = {"method": "add", "params": {"Campaigns": [campaign_spec]}}
    r = await _post_with_retry(f"{API}campaigns", token, body)
    if not r or r.status_code >= 400:
        return None
    res = r.json().get("result", {}).get("AddResults", [])
    if res and "Id" in res[0]:
        return int(res[0]["Id"])
    return None


async def campaigns_suspend(token: str, campaign_ids: list[int]) -> bool:
    if settings.YANDEX_MOCK or not campaign_ids:
        return True
    body = {"method": "suspend", "params": {"SelectionCriteria": {"Ids": campaign_ids}}}
    r = await _post_with_retry(f"{API}campaigns", token, body)
    return bool(r and r.status_code < 400)


async def campaigns_resume(token: str, campaign_ids: list[int]) -> bool:
    if settings.YANDEX_MOCK or not campaign_ids:
        return True
    body = {"method": "resume", "params": {"SelectionCriteria": {"Ids": campaign_ids}}}
    r = await _post_with_retry(f"{API}campaigns", token, body)
    return bool(r and r.status_code < 400)


async def ad_performance_rows(token: str, campaign_ids: list[int]) -> list[dict[str, Any]]:
    if settings.YANDEX_MOCK:
        rows = []
        for cid in campaign_ids:
            rows.extend(
                [
                    {
                        "CampaignId": cid,
                        "Id": cid * 10 + 1,
                        "Title": "Скидка 10% на монтаж",
                        "State": "ON",
                        "Cost": 420.0,
                        "Clicks": 35,
                        "Impressions": 1800,
                    },
                    {
                        "CampaignId": cid,
                        "Id": cid * 10 + 2,
                        "Title": "Бесплатный выезд замерщика",
                        "State": "SUSPENDED",
                        "Cost": 110.0,
                        "Clicks": 8,
                        "Impressions": 640,
                    },
                ]
            )
        return rows
    body = {
        "method": "get",
        "params": {"SelectionCriteria": {"CampaignIds": campaign_ids}, "FieldNames": ["Id", "CampaignId", "State", "Status"]},
    }
    r = await _post_with_retry(f"{API}ads", token, body)
    if not r or r.status_code >= 400:
        return []
    ads = r.json().get("result", {}).get("Ads", []) or []
    # In non-mock mode we do not synthesize fake titles/metrics.
    # Return only raw API fields; optional metrics may be absent.
    out: list[dict[str, Any]] = []
    for a in ads:
        title = ""
        text_ad = a.get("TextAd") if isinstance(a, dict) else None
        if isinstance(text_ad, dict):
            title = str(text_ad.get("Title") or "")
        out.append(
            {
                "CampaignId": a.get("CampaignId"),
                "Id": a.get("Id"),
                "Title": title,
                "State": a.get("State") or a.get("Status") or "",
                "Cost": a.get("Cost"),
                "Clicks": a.get("Clicks"),
                "Impressions": a.get("Impressions"),
            }
        )
    return out

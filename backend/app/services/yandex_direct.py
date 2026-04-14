"""
Yandex Direct API v5 JSON client (Campaigns, Reports). Mock mode for local dev.
Docs: https://yandex.ru/dev/direct/doc/
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

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


async def campaigns_get(token: str) -> list[dict[str, Any]]:
    if settings.YANDEX_MOCK:
        return [
            {"Id": 1001, "Name": "Демо: поиск", "State": "ON", "Status": "ACCEPTED"},
            {"Id": 1002, "Name": "Демо: РСЯ", "State": "SUSPENDED", "Status": "ACCEPTED"},
        ]
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "State", "Status", "DailyBudget"],
        },
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API}campaigns", headers=_headers(token), json=body)
        r.raise_for_status()
        data = r.json()
        return data.get("result", {}).get("Campaigns", []) or []


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
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{API}reports", headers=_headers(token), json=body)
        if r.status_code >= 400:
            return []
        # Real implementation parses TSV from report URL; keep empty for non-mock without full pipeline.
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
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API}keywords", headers=_headers(token), json=body)
        if r.status_code >= 400:
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
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API}keywords", headers=_headers(token), json=body)
        return r.status_code < 400


async def keywords_set_bids(token: str, items: list[dict[str, Any]]) -> bool:
    if settings.YANDEX_MOCK or not items:
        return True
    body = {"method": "setBids", "params": {"Bids": items}}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API}keywords", headers=_headers(token), json=body)
        return r.status_code < 400


async def campaigns_add(token: str, campaign_spec: dict[str, Any]) -> int | None:
    if settings.YANDEX_MOCK:
        return 9000 + int(json.dumps(campaign_spec, sort_keys=True)[:4].encode().hex()[:4], 16) % 10000
    body = {"method": "add", "params": {"Campaigns": [campaign_spec]}}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API}campaigns", headers=_headers(token), json=body)
        if r.status_code >= 400:
            return None
        res = r.json().get("result", {}).get("AddResults", [])
        if res and "Id" in res[0]:
            return int(res[0]["Id"])
        return None

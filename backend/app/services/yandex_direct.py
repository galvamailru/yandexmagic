"""
Yandex Direct API v5 JSON client (Campaigns, Keywords, Ads, Reports).
Docs: https://yandex.ru/dev/direct/doc/
Sandbox: https://yandex.ru/dev/direct/doc/ru/concepts/sandbox
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any
import asyncio

import httpx

from app.config import get_settings

settings = get_settings()

API = "https://api-sandbox.direct.yandex.com/json/v5/" if settings.YANDEX_SANDBOX else "https://api.direct.yandex.com/json/v5/"


def _headers(token: str, client_login: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    resolved_client_login = (client_login or "").strip()
    if resolved_client_login:
        headers["Client-Login"] = resolved_client_login
    return headers


async def _post_with_retry(
    url: str,
    token: str,
    body: dict[str, Any],
    timeout: float = 60.0,
    client_login: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response | None:
    delays = [0.4, 1.0, 2.0]
    for i, delay in enumerate(delays):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                headers = _headers(token, client_login=client_login)
                if extra_headers:
                    headers.update(extra_headers)
                r = await client.post(url, headers=headers, json=body)
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


async def campaigns_get(token: str, client_login: str | None = None) -> list[dict[str, Any]]:
    rows, _meta = await campaigns_get_with_meta(token, client_login=client_login)
    return rows


async def campaigns_get_with_meta(token: str, client_login: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "State", "Status", "DailyBudget"],
        },
    }
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
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


def _parse_tsv(text: str) -> list[dict[str, str]]:
    if not text:
        return []
    s = text.strip("\ufeff\r\n ")
    if not s:
        return []
    f = io.StringIO(s)
    reader = csv.DictReader(f, delimiter="\t")
    out: list[dict[str, str]] = []
    for row in reader:
        if row:
            out.append({k: (v or "") for k, v in row.items() if k})
    return out


def _to_float(v: object) -> float:
    try:
        return float(str(v).replace(",", "."))
    except Exception:  # noqa: BLE001
        return 0.0


def _to_int(v: object) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except Exception:  # noqa: BLE001
        return 0


async def reports_campaign_daily(
    token: str, campaign_ids: list[int], day_from: date, day_to: date, client_login: str | None = None
) -> list[dict[str, Any]]:
    """Return rows with CampaignId, Date, Cost, Clicks, Impressions."""
    body = {
        "params": {
            "SelectionCriteria": {"Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(x) for x in campaign_ids]}]},
            "FieldNames": ["CampaignId", "Date", "Cost", "Clicks", "Impressions"],
            "ReportName": f"ymagic_{day_from}_{day_to}",
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "DateFrom": day_from.isoformat(),
            "DateTo": day_to.isoformat(),
            "Format": "TSV",
            "IncludeVAT": "YES",
            "IncludeDiscount": "NO",
        }
    }
    report_headers = {
        "processingMode": "auto",
        "skipReportHeader": "true",
        "skipColumnHeader": "false",
        "skipReportSummary": "true",
        "returnMoneyInMicros": "false",
    }

    # Sandbox restriction: one campaign per report.
    if settings.YANDEX_SANDBOX and len(campaign_ids) > 1:
        out: list[dict[str, Any]] = []
        for cid in campaign_ids:
            out.extend(await reports_campaign_daily(token, [cid], day_from, day_to, client_login=client_login))
        return out

    r = await _post_with_retry(
        f"{API}reports",
        token,
        body,
        timeout=120.0,
        client_login=client_login,
        extra_headers=report_headers,
    )
    if not r or r.status_code >= 400:
        return []
    rows = _parse_tsv(r.text or "")
    out: list[dict[str, Any]] = []
    for it in rows:
        out.append(
            {
                "CampaignId": _to_int(it.get("CampaignId")),
                "Date": (it.get("Date") or "")[:10],
                "Cost": _to_float(it.get("Cost")),
                "Clicks": _to_int(it.get("Clicks")),
                "Impressions": _to_int(it.get("Impressions")),
            }
        )
    return out


async def keyword_performance_rows(
    token: str, campaign_ids: list[int], client_login: str | None = None
) -> list[dict[str, Any]]:
    """Keyword-level stats for autopilot rules.

    Combine keywords.get (attributes) and Reports keyword performance metrics.
    """
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "Keyword", "CampaignId", "Bid", "Status"],
        },
    }
    r = await _post_with_retry(f"{API}keywords", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return []
    keywords = r.json().get("result", {}).get("Keywords", []) or []
    if not isinstance(keywords, list) or not keywords:
        return []

    report_headers = {
        "processingMode": "auto",
        "skipReportHeader": "true",
        "skipColumnHeader": "false",
        "skipReportSummary": "true",
        "returnMoneyInMicros": "false",
    }

    async def _report_for_campaign(cid: int) -> list[dict[str, str]]:
        rep_body = {
            "params": {
                "SelectionCriteria": {"Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(cid)]}]},
                "FieldNames": ["CampaignId", "KeywordId", "Impressions", "Clicks", "Ctr", "Cost"],
                "ReportName": f"ym_kw_{cid}",
                "ReportType": "KEYWORDS_PERFORMANCE_REPORT",
                "DateRangeType": "LAST_30_DAYS",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "NO",
            }
        }
        rr = await _post_with_retry(
            f"{API}reports",
            token,
            rep_body,
            timeout=120.0,
            client_login=client_login,
            extra_headers=report_headers,
        )
        if not rr or rr.status_code >= 400:
            return []
        return _parse_tsv(rr.text or "")

    ids = list({int(k.get("CampaignId") or 0) for k in keywords if k.get("CampaignId")})
    ids = [x for x in ids if x]
    metrics_rows: list[dict[str, str]] = []
    if settings.YANDEX_SANDBOX:
        for cid in ids:
            metrics_rows.extend(await _report_for_campaign(cid))
    else:
        rep_body = {
            "params": {
                "SelectionCriteria": {"Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(x) for x in ids]}]},
                "FieldNames": ["CampaignId", "KeywordId", "Impressions", "Clicks", "Ctr", "Cost"],
                "ReportName": "ym_kw_multi",
                "ReportType": "KEYWORDS_PERFORMANCE_REPORT",
                "DateRangeType": "LAST_30_DAYS",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "NO",
            }
        }
        rr = await _post_with_retry(
            f"{API}reports",
            token,
            rep_body,
            timeout=120.0,
            client_login=client_login,
            extra_headers=report_headers,
        )
        if rr and rr.status_code < 400:
            metrics_rows = _parse_tsv(rr.text or "")

    metrics_by_id: dict[int, dict[str, str]] = {}
    for it in metrics_rows:
        kid = _to_int(it.get("KeywordId"))
        if kid:
            metrics_by_id[kid] = it

    out: list[dict[str, Any]] = []
    for k in keywords:
        kid = int(k.get("Id") or 0)
        m = metrics_by_id.get(kid) or {}
        status = str(k.get("Status") or "")
        out.append(
            {
                "CampaignId": int(k.get("CampaignId") or 0),
                "Id": kid,
                "Keyword": str(k.get("Keyword") or ""),
                "Bid": _to_float(k.get("Bid") or 0),
                "Status": status,
                # Compatibility with existing UI mapping
                "UserParam1": status,
                "Cost": _to_float(m.get("Cost")),
                "Ctr": _to_float(m.get("Ctr")),
                "Clicks": _to_int(m.get("Clicks")),
                "Impressions": _to_int(m.get("Impressions")),
            }
        )
    return out


async def keywords_suspend(token: str, keyword_ids: list[int], client_login: str | None = None) -> bool:
    if not keyword_ids:
        return True
    body = {
        "method": "suspend",
        "params": {
            "SelectionCriteria": {"Ids": keyword_ids},
        },
    }
    r = await _post_with_retry(f"{API}keywords", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def keywords_resume(token: str, keyword_ids: list[int], client_login: str | None = None) -> bool:
    if not keyword_ids:
        return True
    body = {
        "method": "resume",
        "params": {"SelectionCriteria": {"Ids": keyword_ids}},
    }
    r = await _post_with_retry(f"{API}keywords", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def keywords_set_bids(token: str, items: list[dict[str, Any]], client_login: str | None = None) -> bool:
    if not items:
        return True
    body = {"method": "setBids", "params": {"Bids": items}}
    r = await _post_with_retry(f"{API}keywords", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def campaigns_add(token: str, campaign_spec: dict[str, Any], client_login: str | None = None) -> int | None:
    body = {"method": "add", "params": {"Campaigns": [campaign_spec]}}
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return None
    res = r.json().get("result", {}).get("AddResults", [])
    if res and "Id" in res[0]:
        return int(res[0]["Id"])
    return None


async def campaigns_suspend(token: str, campaign_ids: list[int], client_login: str | None = None) -> bool:
    if not campaign_ids:
        return True
    body = {"method": "suspend", "params": {"SelectionCriteria": {"Ids": campaign_ids}}}
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def campaigns_resume(token: str, campaign_ids: list[int], client_login: str | None = None) -> bool:
    if not campaign_ids:
        return True
    body = {"method": "resume", "params": {"SelectionCriteria": {"Ids": campaign_ids}}}
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def campaigns_get_negative_keywords(
    token: str, campaign_id: int, client_login: str | None = None
) -> list[str]:
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"Ids": [campaign_id]},
            "FieldNames": ["Id"],
            "TextCampaignFieldNames": ["NegativeKeywords"],
        },
    }
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return []
    campaigns = r.json().get("result", {}).get("Campaigns", []) or []
    if not campaigns:
        return []
    tc = campaigns[0].get("TextCampaign") if isinstance(campaigns[0], dict) else {}
    if not isinstance(tc, dict):
        return []
    nk = tc.get("NegativeKeywords")
    if isinstance(nk, dict) and isinstance(nk.get("Items"), list):
        return [str(x).strip() for x in nk["Items"] if str(x).strip()]
    return []


async def campaigns_add_negative_keywords(
    token: str, campaign_id: int, keywords: list[str], client_login: str | None = None
) -> bool:
    current = await campaigns_get_negative_keywords(token, campaign_id, client_login=client_login)
    merged = list(dict.fromkeys([*current, *[str(x).strip() for x in keywords if str(x).strip()]]))
    if not merged:
        return True
    body = {
        "method": "update",
        "params": {
            "Campaigns": [
                {
                    "Id": campaign_id,
                    "TextCampaign": {"NegativeKeywords": {"Items": merged[:1000]}},
                }
            ]
        },
    }
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def ad_performance_rows(token: str, campaign_ids: list[int], client_login: str | None = None) -> list[dict[str, Any]]:
    body = {
        "method": "get",
        "params": {"SelectionCriteria": {"CampaignIds": campaign_ids}, "FieldNames": ["Id", "CampaignId", "State", "Status", "TextAd"]},
    }
    r = await _post_with_retry(f"{API}ads", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return []
    ads = r.json().get("result", {}).get("Ads", []) or []
    if not isinstance(ads, list) or not ads:
        return []

    report_headers = {
        "processingMode": "auto",
        "skipReportHeader": "true",
        "skipColumnHeader": "false",
        "skipReportSummary": "true",
        "returnMoneyInMicros": "false",
    }

    async def _report_for_campaign(cid: int) -> list[dict[str, str]]:
        rep_body = {
            "params": {
                "SelectionCriteria": {"Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(cid)]}]},
                "FieldNames": ["CampaignId", "AdId", "Impressions", "Clicks", "Cost"],
                "ReportName": f"ym_ad_{cid}",
                "ReportType": "AD_PERFORMANCE_REPORT",
                "DateRangeType": "LAST_30_DAYS",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "NO",
            }
        }
        rr = await _post_with_retry(
            f"{API}reports",
            token,
            rep_body,
            timeout=120.0,
            client_login=client_login,
            extra_headers=report_headers,
        )
        if not rr or rr.status_code >= 400:
            return []
        return _parse_tsv(rr.text or "")

    ids = list({int(a.get("CampaignId") or 0) for a in ads if isinstance(a, dict) and a.get("CampaignId")})
    ids = [x for x in ids if x]
    metrics_rows: list[dict[str, str]] = []
    if settings.YANDEX_SANDBOX:
        for cid in ids:
            metrics_rows.extend(await _report_for_campaign(cid))
    else:
        rep_body = {
            "params": {
                "SelectionCriteria": {"Filter": [{"Field": "CampaignId", "Operator": "IN", "Values": [str(x) for x in ids]}]},
                "FieldNames": ["CampaignId", "AdId", "Impressions", "Clicks", "Cost"],
                "ReportName": "ym_ad_multi",
                "ReportType": "AD_PERFORMANCE_REPORT",
                "DateRangeType": "LAST_30_DAYS",
                "Format": "TSV",
                "IncludeVAT": "YES",
                "IncludeDiscount": "NO",
            }
        }
        rr = await _post_with_retry(
            f"{API}reports",
            token,
            rep_body,
            timeout=120.0,
            client_login=client_login,
            extra_headers=report_headers,
        )
        if rr and rr.status_code < 400:
            metrics_rows = _parse_tsv(rr.text or "")

    metrics_by_id: dict[int, dict[str, str]] = {}
    for it in metrics_rows:
        aid = _to_int(it.get("AdId"))
        if aid:
            metrics_by_id[aid] = it

    out: list[dict[str, Any]] = []
    for a in ads:
        if not isinstance(a, dict):
            continue
        ad_id = int(a.get("Id") or 0)
        m = metrics_by_id.get(ad_id) or {}
        title = ""
        text_ad = a.get("TextAd")
        if isinstance(text_ad, dict):
            title = str(text_ad.get("Title") or "")
        out.append(
            {
                "CampaignId": int(a.get("CampaignId") or 0),
                "Id": ad_id,
                "Title": title,
                "State": a.get("State") or a.get("Status") or "",
                "Cost": _to_float(m.get("Cost")),
                "Clicks": _to_int(m.get("Clicks")),
                "Impressions": _to_int(m.get("Impressions")),
            }
        )
    return out


async def ads_suspend(token: str, ad_ids: list[int], client_login: str | None = None) -> bool:
    if not ad_ids:
        return True
    body = {"method": "suspend", "params": {"SelectionCriteria": {"Ids": ad_ids}}}
    r = await _post_with_retry(f"{API}ads", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def ads_resume(token: str, ad_ids: list[int], client_login: str | None = None) -> bool:
    if not ad_ids:
        return True
    body = {"method": "resume", "params": {"SelectionCriteria": {"Ids": ad_ids}}}
    r = await _post_with_retry(f"{API}ads", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def campaigns_update_daily_budget(
    token: str, campaign_id: int, amount_rub: float, client_login: str | None = None
) -> bool:
    amount_micros = int(max(300.0, amount_rub) * 1_000_000)
    body = {
        "method": "update",
        "params": {
            "Campaigns": [
                {
                    "Id": campaign_id,
                    "DailyBudget": {"Amount": amount_micros, "Mode": "STANDARD"},
                }
            ]
        },
    }
    r = await _post_with_retry(f"{API}campaigns", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def audience_targets_get(token: str, campaign_ids: list[int], client_login: str | None = None) -> list[dict[str, Any]]:
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "State", "BidModifier"],
        },
    }
    r = await _post_with_retry(f"{API}audiencetargets", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return []
    return r.json().get("result", {}).get("AudienceTargets", []) or []


async def audience_targets_update_bid_modifier(
    token: str, audience_target_id: int, bid_modifier_percent: int, client_login: str | None = None
) -> bool:
    body = {
        "method": "update",
        "params": {
            "AudienceTargets": [
                {
                    "Id": audience_target_id,
                    "BidModifier": int(max(10, min(1200, bid_modifier_percent))),
                }
            ]
        },
    }
    r = await _post_with_retry(f"{API}audiencetargets", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def retargetinglists_get(token: str, client_login: str | None = None) -> list[dict[str, Any]]:
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "Description", "Type"],
        },
    }
    r = await _post_with_retry(f"{API}retargetinglists", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return []
    return r.json().get("result", {}).get("RetargetingLists", []) or []


async def bidmodifiers_get(token: str, campaign_ids: list[int], client_login: str | None = None) -> list[dict[str, Any]]:
    body = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["CampaignId", "AdGroupId", "Type"],
            "MobileAdjustmentFieldNames": ["BidModifier"],
            "DesktopAdjustmentFieldNames": ["BidModifier"],
            "DemographicsAdjustmentFieldNames": ["BidModifier", "Age", "Gender"],
            "RetargetingAdjustmentFieldNames": ["BidModifier", "Conditions"],
        },
    }
    r = await _post_with_retry(f"{API}bidmodifiers", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return []
    return r.json().get("result", {}).get("BidModifiers", []) or []


async def bidmodifiers_update_mobile(
    token: str, campaign_id: int, bid_modifier_percent: int, client_login: str | None = None
) -> bool:
    body = {
        "method": "add",
        "params": {
            "BidModifiers": [
                {
                    "CampaignId": campaign_id,
                    "MobileAdjustment": {"BidModifier": int(max(10, min(1200, bid_modifier_percent)))},
                }
            ]
        },
    }
    r = await _post_with_retry(f"{API}bidmodifiers", token, body, client_login=client_login)
    return bool(r and r.status_code < 400)


async def changes_check(
    token: str,
    campaign_ids: list[int],
    last_change_timestamp: str | None = None,
    client_login: str | None = None,
) -> dict[str, Any]:
    body = {
        "method": "checkCampaigns",
        "params": {
            "CampaignIds": campaign_ids,
            "Timestamp": last_change_timestamp or "1970-01-01T00:00:00Z",
        },
    }
    r = await _post_with_retry(f"{API}changes", token, body, client_login=client_login)
    if not r or r.status_code >= 400:
        return {"Changed": False, "Timestamp": last_change_timestamp or ""}
    return r.json().get("result", {}) or {}

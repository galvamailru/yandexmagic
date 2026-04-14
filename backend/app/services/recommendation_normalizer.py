import json
import re
from typing import Any


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind", "general")).strip() or "general"
    title = str(item.get("title", "Рекомендация")).strip() or "Рекомендация"
    body = str(item.get("body", "")).strip()
    payload = item.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return {"kind": kind, "title": title, "body": body, "payload": payload}


def _json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    candidates.extend(x.strip() for x in fenced if x.strip())
    return candidates


def parse_structured_recommendations(text: str) -> list[dict[str, Any]]:
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            out = [normalize_item(x) for x in parsed if isinstance(x, dict)]
            if out:
                return out
        if isinstance(parsed, dict) and isinstance(parsed.get("recommendations"), list):
            out = [normalize_item(x) for x in parsed["recommendations"] if isinstance(x, dict)]
            if out:
                return out
    return []


def sanitize_unstructured_body(text: str) -> str:
    t = text.strip()
    t = re.sub(r"```(?:json)?", "", t, flags=re.IGNORECASE)
    t = t.replace("```", "")
    return t.strip()

import json
import re
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.domain_action_contracts import contract_hint, validate_domain_actions
from app.services.prompt_store import get_domain_prompt
from app.services.recommendation_normalizer import parse_structured_recommendations, sanitize_unstructured_body

settings = get_settings()


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "sk-mock",
        base_url=settings.LLM_BASE_URL,
    )


def generate_recommendations(stats_summary: str, db: Session | None = None, domain: str | None = None) -> list[dict[str, Any]]:
    if not (settings.LLM_API_KEY or settings.OPENAI_API_KEY):
        return [
            {
                "kind": "keyword",
                "title": "Отключите низкоэффективную фразу",
                "body": "Фраза «пример» тратит бюджет при низком CTR.",
                "payload": {"keyword_id": 0},
            }
        ]
    if not db or not domain:
        return []
    system_prompt = get_domain_prompt(db, domain).strip()
    if not system_prompt:
        return []
    resp = _client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": stats_summary},
        ],
        temperature=0.3,
    )
    text = resp.choices[0].message.content or "[]"
    parsed = parse_structured_recommendations(text)
    if parsed:
        return parsed
    # Keep one strict fallback shape so UI format is always uniform.
    body = sanitize_unstructured_body(text)
    body = re.sub(r"\s+", " ", body).strip()[:1200]
    low = body.lower()
    if "не могу проанализировать" in low or "нет доступа" in low:
        body = "Анализ не сформирован в структурированном формате. Проверьте доступ к данным и повторите генерацию."
    return [{"kind": "general", "title": "Анализ", "body": body, "payload": {"format": "fallback"}}]


def generate_ad_texts(business_summary: str, keywords: list[str]) -> list[dict[str, str]]:
    if not (settings.LLM_API_KEY or settings.OPENAI_API_KEY):
        return [
            {"title": "Заголовок 1", "title2": "Уточнение", "text": "Текст объявления с УТП."},
            {"title": "Заголовок 2", "title2": "Доставка", "text": "Закажите онлайн, быстрая доставка."},
        ]
    kw = ", ".join(keywords[:30])
    resp = _client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Сгенерируй 3 варианта объявлений для Яндекс Директ. Ответ только JSON: "
                'массив {title, title2, text}.',
            },
            {"role": "user", "content": f"Бизнес: {business_summary}\nКлючи: {kw}"},
        ],
        temperature=0.6,
    )
    text = resp.choices[0].message.content or "[]"
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return [{"title": "Объявление", "title2": "", "text": text[:500]}]


def generate_domain_actions(
    domain: str,
    data_summary: str,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    if not (settings.LLM_API_KEY or settings.OPENAI_API_KEY):
        return []
    if db is None:
        return []
    base_prompt = get_domain_prompt(db, domain).strip()
    if not base_prompt:
        return []
    system_prompt = f"{base_prompt}\n\n{contract_hint(domain)}"
    try:
        resp = _client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": data_summary[:8000]},
            ],
            temperature=0.1,
        )
    except Exception:  # noqa: BLE001
        return []
    text = resp.choices[0].message.content or "[]"
    items = parse_structured_recommendations(text)
    # parse_structured_recommendations normalizes to {kind,title,body,payload}, so also support raw JSON list
    if items:
        raw: list[dict[str, Any]] = []
        for it in items:
            payload = it.get("payload")
            if isinstance(payload, dict) and payload.get("action_type"):
                raw.append(payload)
        if raw:
            return validate_domain_actions(domain, raw)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return validate_domain_actions(domain, [x for x in parsed if isinstance(x, dict)])
    except json.JSONDecodeError:
        pass
    return []

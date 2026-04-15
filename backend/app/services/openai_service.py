import json
import re
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.prompt_store import get_ai_prompt
from app.services.recommendation_normalizer import parse_structured_recommendations, sanitize_unstructured_body

settings = get_settings()


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "sk-mock",
        base_url=settings.LLM_BASE_URL,
    )


def generate_recommendations(stats_summary: str, db: Session | None = None) -> list[dict[str, Any]]:
    if not (settings.LLM_API_KEY or settings.OPENAI_API_KEY):
        return [
            {
                "kind": "keyword",
                "title": "Отключите низкоэффективную фразу",
                "body": "Фраза «пример» тратит бюджет при низком CTR.",
                "payload": {"keyword_id": 0},
            }
        ]
    system_prompt = get_ai_prompt(db) if db is not None else (
        "Ты эксперт по Яндекс Директ. Ответь ТОЛЬКО JSON-массивом объектов "
        "{kind,title,body,payload} без markdown и текста вне JSON. "
        "Payload contract обязателен: payload всегда объект; "
        "для kind=keyword укажи action и keyword_id; "
        "для kind=ad укажи action и ad_id; "
        "для kind=bid укажи action, keyword_id, percent; "
        "для kind=budget укажи action, amount, period; "
        "для kind=general укажи action=none и note. "
        "Если данных недостаточно, верни один объект с title='Анализ'."
    )
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

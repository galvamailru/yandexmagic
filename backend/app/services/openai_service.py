import json
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.prompt_store import get_ai_prompt

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
        "{kind,title,body,payload} с конкретными рекомендациями по русски."
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
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return [{"kind": "general", "title": "Анализ", "body": text[:2000], "payload": {}}]


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

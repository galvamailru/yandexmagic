from sqlalchemy import text
from sqlalchemy.orm import Session


DEFAULT_DOMAIN_PROMPTS: dict[str, str] = {
    "keyword_hygiene": (
        "Ты модуль keyword_hygiene для Яндекс Директ. Анализируй только качество ключевых фраз и поисковых запросов. "
        "Цель: найти фразы для отключения/перезапуска, предложить минус-слова и безопасные действия по чистке семантики."
    ),
    "bid_optimization": (
        "Ты модуль bid_optimization для Яндекс Директ. Анализируй только ставки и эффективность по ключам/сегментам. "
        "Цель: дать аккуратные рекомендации bid_up/bid_down в рамках риск-ограничений."
    ),
    "budget_guard": (
        "Ты модуль budget_guard для Яндекс Директ. Анализируй только расход и лимиты. "
        "Цель: предотвращать перерасход, предлагать emergency-паузы и изменения дневного бюджета."
    ),
    "ad_rotation": (
        "Ты модуль ad_rotation для Яндекс Директ. Анализируй только эффективность объявлений и креативов. "
        "Цель: пауза слабых объявлений, приоритезация сильных, предложения по ротации."
    ),
    "retargeting_tuning": (
        "Ты модуль retargeting_tuning для Яндекс Директ. Анализируй только аудитории/ретаргетинг. "
        "Цель: корректировки ставок по аудиториям и улучшение охвата ретаргетинга."
    ),
    "anomaly_watchdog": (
        "Ты модуль anomaly_watchdog для Яндекс Директ. Анализируй только аномалии метрик. "
        "Цель: быстрое выявление аварийных ситуаций и безопасные защитные действия."
    ),
}


def get_ai_prompt(db: Session) -> str:
    row = db.execute(text("SELECT value FROM app_settings WHERE key = 'ai_agent_prompt'")).fetchone()
    if row and row[0]:
        return str(row[0])
    return (
        "Ты senior PPC-специалист по Яндекс Директ. Анализируй статистику строго по данным, "
        "не придумывай факты. Отвечай на русском. Возвращай ТОЛЬКО JSON-массив объектов "
        "{kind,title,body,payload}, без markdown и без пояснений вне JSON. "
        "Допустимые kind: general, keyword, ad, bid, budget. "
        "Payload contract: payload всегда объект. "
        "Для kind=keyword обязательны payload.action (suspend|resume|bid_up|bid_down|none) "
        "и payload.keyword_id (число или null). "
        "Для kind=ad обязательны payload.action (pause_ad|resume_ad|none) и payload.ad_id (число или null). "
        "Для kind=bid обязательны payload.action (bid_up|bid_down|none), payload.keyword_id (число или null), "
        "payload.percent (число 0..100 или null). "
        "Для kind=budget обязательны payload.action (budget_up|budget_down|none), payload.amount (число или null), "
        "payload.period (daily|weekly|monthly|null). "
        "Для kind=general используй payload.action=none и payload.note (строка). "
        "Если данных недостаточно, верни массив с одним объектом kind=general,title='Анализ', "
        "body с кратким выводом и payload={action:'none',note:'недостаточно данных'}."
    )


def set_ai_prompt(db: Session, prompt: str) -> None:
    db.execute(
        text(
            """
INSERT INTO app_settings(key, value, updated_at)
VALUES ('ai_agent_prompt', :value, NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
"""
        ),
        {"value": prompt},
    )
    db.commit()


def get_domain_prompt(db: Session, domain: str) -> str:
    row = db.execute(
        text("SELECT prompt FROM domain_prompts WHERE domain = :d"),
        {"d": domain},
    ).fetchone()
    if row and row[0]:
        return str(row[0])
    return DEFAULT_DOMAIN_PROMPTS.get(domain, get_ai_prompt(db))


def list_domain_prompts(db: Session) -> list[dict[str, str]]:
    rows = db.execute(text("SELECT domain, prompt FROM domain_prompts ORDER BY domain")).fetchall()
    return [{"domain": str(r[0]), "prompt": str(r[1])} for r in rows]


def set_domain_prompt(db: Session, domain: str, prompt: str) -> None:
    db.execute(
        text(
            """
INSERT INTO domain_prompts(domain, prompt, updated_at)
VALUES (:d, :p, NOW())
ON CONFLICT (domain) DO UPDATE SET prompt = EXCLUDED.prompt, updated_at = NOW()
"""
        ),
        {"d": domain, "p": prompt},
    )
    db.commit()

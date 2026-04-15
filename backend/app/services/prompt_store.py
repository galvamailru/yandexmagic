from sqlalchemy import text
from sqlalchemy.orm import Session


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

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_ai_prompt(db: Session) -> str:
    row = db.execute(text("SELECT value FROM app_settings WHERE key = 'ai_agent_prompt'")).fetchone()
    if row and row[0]:
        return str(row[0])
    return (
        "Ты senior PPC-специалист по Яндекс Директ. Анализируй статистику строго по данным, "
        "не придумывай факты. Отвечай на русском."
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

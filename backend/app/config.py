from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://yandexmagic:yandexmagic@localhost:5432/yandexmagic"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-change-in-production"
    CORS_ORIGINS: str = "http://localhost:3000"

    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""
    YANDEX_REDIRECT_URI: str = "http://localhost:3000/auth/callback"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    PLATFORM_ADMIN_YANDEX_IDS: str = ""
    YANDEX_MOCK: bool = False

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def platform_admin_id_set(self) -> set[str]:
        return {x.strip() for x in self.PLATFORM_ADMIN_YANDEX_IDS.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/meta", tags=["meta"])
settings = get_settings()


@router.get("")
def meta() -> dict[str, bool]:
    return {"yandex_sandbox": bool(settings.YANDEX_SANDBOX)}


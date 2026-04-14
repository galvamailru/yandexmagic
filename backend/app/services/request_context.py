import uuid
from contextvars import ContextVar

_corr_id: ContextVar[str] = ContextVar("corr_id", default="")


def set_correlation_id(value: str | None = None) -> str:
    cid = value or str(uuid.uuid4())
    _corr_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return _corr_id.get() or ""

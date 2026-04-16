from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.routers import admin, auth, campaigns, dashboard, me, meta, wizard
from app.services.request_context import set_correlation_id
from app.services.bootstrap import init_public_schema

settings = get_settings()

app = FastAPI(title="YandexMagic API", version="0.1.0")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or ""
        cid = set_correlation_id(cid or None)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(auth.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(wizard.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_public_schema()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

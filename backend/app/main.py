from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, auth, campaigns, dashboard, me, wizard
from app.services.bootstrap import init_public_schema

settings = get_settings()

app = FastAPI(title="YandexMagic API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(wizard.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_public_schema()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

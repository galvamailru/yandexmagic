from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_tenant_access
from app.models.public import Tenant
from app.repositories import tenant_queries as tq
from app.schemas.common import DashboardSummary, RecommendationOut, SpendPoint

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> DashboardSummary:
    c, spend, cpc = tq.dashboard_totals(db, tenant.schema_name)
    return DashboardSummary(campaigns_count=c, total_spend_rub=spend, avg_cpc_rub=cpc)


@router.get("/spend-chart", response_model=list[SpendPoint])
def spend_chart(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    days: int = 14,
) -> list[SpendPoint]:
    rows = tq.spend_by_day(db, tenant.schema_name, days=days)
    return [SpendPoint(date=r["date"], cost_rub=r["cost_rub"]) for r in rows]


@router.get("/recommendations", response_model=list[RecommendationOut])
def recent_recs(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    limit: int = 20,
) -> list[RecommendationOut]:
    rows = tq.recent_recommendations(db, tenant.schema_name, limit=limit)
    return [
        RecommendationOut(
            id=r["id"],  # type: ignore[arg-type]
            campaign_id=r["campaign_id"],  # type: ignore[arg-type]
            kind=r["kind"],
            title=r["title"],
            body=r["body"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]

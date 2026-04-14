from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_tenant_access
from app.models.public import Tenant
from app.repositories import tenant_queries as tq
from app.schemas.common import CampaignOut, DashboardSummary, RecommendationAnalyticsOut, RecommendationOut, SpendPoint
from sqlalchemy import text

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


@router.get("/campaigns-options", response_model=list[CampaignOut])
def campaign_options(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> list[CampaignOut]:
    rows = tq.list_campaigns(db, tenant.schema_name)
    return [CampaignOut(**r) for r in rows]  # type: ignore[arg-type]


@router.get("/recommendations-analytics", response_model=list[RecommendationAnalyticsOut])
def recommendations_analytics(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
    campaign_id: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[RecommendationAnalyticsOut]:
    cid = None
    if campaign_id:
        from uuid import UUID

        cid = UUID(campaign_id)
    rows = tq.recommendations_analytics(
        db,
        tenant.schema_name,
        campaign_id=cid,
        status=status,
        kind=kind,
        search=search,
        limit=limit,
    )
    return [
        RecommendationAnalyticsOut(
            id=r["id"],  # type: ignore[arg-type]
            campaign_id=r["campaign_id"],  # type: ignore[arg-type]
            campaign_name=r["campaign_name"],
            kind=r["kind"],
            title=r["title"],
            body=r["body"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/automation-kpis")
def automation_kpis(
    db: Annotated[Session, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(require_tenant_access)],
) -> dict:
    schema = tenant.schema_name
    db.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    rec_total = int(db.execute(text(f'SELECT COUNT(*) FROM "{schema}".recommendations')).scalar() or 0)
    rec_pending = int(db.execute(text(f"SELECT COUNT(*) FROM \"{schema}\".recommendations WHERE status='pending'")).scalar() or 0)
    rec_applied = int(db.execute(text(f"SELECT COUNT(*) FROM \"{schema}\".recommendations WHERE status='applied'")).scalar() or 0)
    actions_7d = int(
        db.execute(
            text(f"SELECT COUNT(*) FROM \"{schema}\".action_history WHERE created_at >= NOW() - INTERVAL '7 days'")
        ).scalar()
        or 0
    )
    campaigns_total = int(db.execute(text(f'SELECT COUNT(*) FROM "{schema}".campaigns')).scalar() or 0)
    campaigns_autopilot = int(
        db.execute(text(f"SELECT COUNT(*) FROM \"{schema}\".campaigns WHERE mode='autopilot'")).scalar() or 0
    )
    return {
        "recommendations_total": rec_total,
        "recommendations_pending": rec_pending,
        "recommendations_applied": rec_applied,
        "recommendations_apply_rate_pct": round((rec_applied / rec_total) * 100, 2) if rec_total else 0.0,
        "actions_7d": actions_7d,
        "campaigns_total": campaigns_total,
        "campaigns_autopilot": campaigns_autopilot,
        "autopilot_share_pct": round((campaigns_autopilot / campaigns_total) * 100, 2) if campaigns_total else 0.0,
    }

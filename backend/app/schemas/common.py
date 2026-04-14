from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    login: str
    email: str | None
    display_name: str | None
    is_platform_admin: bool
    autopilot_risk_accepted_at: datetime | None


class TenantBrief(BaseModel):
    id: UUID
    name: str
    schema_name: str


class DashboardSummary(BaseModel):
    campaigns_count: int
    total_spend_rub: Decimal
    avg_cpc_rub: Decimal | None


class SpendPoint(BaseModel):
    date: str
    cost_rub: float


class RecommendationOut(BaseModel):
    id: UUID
    campaign_id: UUID | None
    kind: str
    title: str
    body: str
    status: str
    created_at: str | None


class RecommendationAnalyticsOut(BaseModel):
    id: UUID
    campaign_id: UUID | None
    campaign_name: str | None
    kind: str
    title: str
    body: str
    status: str
    created_at: str | None


class CampaignOut(BaseModel):
    id: UUID
    yandex_campaign_id: int
    name: str
    state: str
    mode: str
    created_at: str | None = None


class CampaignModeBody(BaseModel):
    mode: str = Field(pattern="^(monitoring|advisor|autopilot)$")


class AutopilotRiskBody(BaseModel):
    accept: bool = True


class YandexAuthUrl(BaseModel):
    url: str
    state: str


class OAuthCallbackBody(BaseModel):
    code: str
    state: str | None = None


class SwitchTenantBody(BaseModel):
    tenant_id: UUID


class AdminTenantOut(BaseModel):
    id: UUID
    name: str
    schema_name: str
    is_blocked: bool
    created_at: datetime | None


class WizardStep1(BaseModel):
    site_url: str
    budget_rub: float
    geo: str
    goal: str


class WizardStep2Result(BaseModel):
    keywords: list[str]
    groups: list[list[str]]
    ads: list[dict[str, Any]]


class WizardStep3Body(BaseModel):
    ads: list[dict[str, Any]]


class WizardLaunchBody(BaseModel):
    accept_autopilot_risk: bool = False


class AgentLogOut(BaseModel):
    id: UUID
    campaign_id: UUID | None
    level: str
    message: str
    details: dict[str, Any]
    created_at: str | None

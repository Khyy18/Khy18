from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth Schemas ----------


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    tenant_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: str
    tenant_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Campaign Schemas ----------


class CampaignCreate(BaseModel):
    name: str
    icp_filter: dict[str, Any] = {}
    sequence_id: Optional[UUID] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    icp_filter: Optional[dict[str, Any]] = None
    sequence_id: Optional[UUID] = None


class CampaignResponse(BaseModel):
    id: UUID
    name: str
    icp_filter: dict[str, Any]
    sequence_id: Optional[UUID]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    limit: int
    offset: int


# ---------- Lead Schemas ----------


class LeadCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    company: str
    title: str
    linkedin_url: Optional[str] = None


class LeadUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    status: Optional[str] = None
    score: Optional[float] = None


class LeadResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    company: str
    title: str
    linkedin_url: Optional[str]
    status: str
    score: Optional[float]
    enrichment_data: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    total: int
    limit: int
    offset: int


class LeadImportResponse(BaseModel):
    imported_count: int


# ---------- Sequence Schemas ----------

# Valid channel types for sequence steps
VALID_STEP_CHANNELS = {"email", "linkedin_view", "linkedin_connect", "linkedin_message"}


class SequenceCreate(BaseModel):
    name: str
    steps: list[dict[str, Any]] = []


class SequenceUpdate(BaseModel):
    name: Optional[str] = None
    steps: Optional[list[dict[str, Any]]] = None


class SequenceResponse(BaseModel):
    id: UUID
    name: str
    steps: list[dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


class SequenceListResponse(BaseModel):
    items: list[SequenceResponse]
    total: int
    limit: int
    offset: int


# ---------- Analytics Schemas ----------


class FunnelResponse(BaseModel):
    funnel: dict[str, int]


class CampaignStatsResponse(BaseModel):
    total_leads: int
    messages_sent: int
    open_rate: float
    click_rate: float
    reply_rate: float
    book_rate: float


class TimelineDataPoint(BaseModel):
    date: date
    sends: int
    opens: int
    clicks: int
    replies: int


class TimelineResponse(BaseModel):
    data: list[TimelineDataPoint]


class TopSequenceItem(BaseModel):
    id: UUID
    name: str
    reply_rate: float
    total_messages: int


class TopSequencesResponse(BaseModel):
    items: list[TopSequenceItem]


# ---------- Optimizer / A/B Test Schemas ----------


class ABTestVariantInput(BaseModel):
    key: str
    subject: Optional[str] = None
    body: Optional[str] = None
    template_config: Optional[dict[str, Any]] = None


class ABTestCreate(BaseModel):
    campaign_id: UUID
    name: str
    variants: list[ABTestVariantInput]
    min_sends_per_variant: int = 100


class ABTestResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    name: str
    status: str
    variants: list[dict[str, Any]]
    created_at: datetime
    completed_at: Optional[datetime] = None
    winner_variant_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ABTestListResponse(BaseModel):
    items: list[ABTestResponse]
    total: int


class ABTestResultsResponse(BaseModel):
    test_id: str
    status: str
    variants: list[dict[str, Any]]
    is_significant: bool
    p_value: float
    winner_key: Optional[str] = None


class SuggestionResponse(BaseModel):
    suggestions: list[dict[str, Any]]


class SendTimeResponse(BaseModel):
    optimal_times: list[dict[str, Any]]


# ---------- Billing Schemas ----------


class PlanResponse(BaseModel):
    id: UUID
    name: str
    leads_limit: int
    emails_limit: int
    linkedin_limit: int
    campaigns_limit: int
    price_cents: int
    stripe_price_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionResponse(BaseModel):
    id: UUID
    plan: PlanResponse
    status: str
    stripe_subscription_id: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UsageResponse(BaseModel):
    leads_used: int
    leads_limit: int
    emails_used: int
    emails_limit: int
    linkedin_used: int
    linkedin_limit: int
    campaigns_active: int
    campaigns_limit: int
    period_start: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class ChangePlanRequest(BaseModel):
    plan_id: UUID


class SubscribeRequest(BaseModel):
    plan_id: UUID
    success_url: str
    cancel_url: str


class InvoiceResponse(BaseModel):
    id: str
    amount_due: int
    status: str
    created: datetime
    hosted_invoice_url: Optional[str] = None

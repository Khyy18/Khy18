from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


# ---------- Auth Schemas ----------


class UserCreate(BaseModel):
    email: EmailStr
    password: str
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

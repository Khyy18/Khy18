import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------- Enums ----------

class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    replied = "replied"
    qualified = "qualified"
    booked = "booked"
    lost = "lost"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"


class ChannelType(str, enum.Enum):
    email = "email"
    linkedin = "linkedin"
    twitter = "twitter"


class UserRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class MessageDirection(str, enum.Enum):
    outbound = "outbound"
    inbound = "inbound"


class MessageStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    opened = "opened"
    clicked = "clicked"
    replied = "replied"
    bounced = "bounced"


class EventType(str, enum.Enum):
    open = "open"
    click = "click"
    reply = "reply"
    bounce = "bounce"
    unsubscribe = "unsubscribe"


class ABTestStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    paused = "paused"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    trialing = "trialing"


class PlanName(str, enum.Enum):
    starter = "starter"
    growth = "growth"
    agency = "agency"
    enterprise = "enterprise"


class OnboardingStep(str, enum.Enum):
    tenant_created = "tenant_created"
    smtp_connected = "smtp_connected"
    icp_uploaded = "icp_uploaded"
    campaign_activated = "campaign_activated"
    completed = "completed"


# ---------- Utility ----------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------- Models ----------

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=False)
    settings = Column(JSONB, default=dict)
    brand_settings = Column(JSONB, default=dict)
    onboarding_step = Column(
        Enum(OnboardingStep), default=OnboardingStep.tenant_created, nullable=True
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    leads = relationship("Lead", back_populates="tenant")
    campaigns = relationship("Campaign", back_populates="tenant")
    sequences = relationship("Sequence", back_populates="tenant")
    users = relationship("User", back_populates="tenant")
    ab_tests = relationship("ABTest", back_populates="tenant")
    subscriptions = relationship("Subscription", back_populates="tenant")
    usage_records = relationship("UsageRecord", back_populates="tenant")
    api_keys = relationship("ApiKey", back_populates="tenant")
    webhooks = relationship("Webhook", back_populates="tenant")
    lead_feedbacks = relationship("LeadFeedback", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.member, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    tenant = relationship("Tenant", back_populates="users")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String, nullable=False)
    linkedin_url = Column(String, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    company = Column(String, nullable=False)
    title = Column(String, nullable=False)
    enrichment_data = Column(JSONB, default=dict)
    status = Column(Enum(LeadStatus), default=LeadStatus.new, nullable=False)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    tenant = relationship("Tenant", back_populates="leads")
    messages = relationship("Message", back_populates="lead")
    pending_approvals = relationship("PendingApproval", back_populates="lead")


class Sequence(Base):
    __tablename__ = "sequences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    steps = Column(JSONB, default=list)

    tenant = relationship("Tenant", back_populates="sequences")
    campaigns = relationship("Campaign", back_populates="sequence")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    icp_filter = Column(JSONB, default=dict)
    sequence_id = Column(
        UUID(as_uuid=True), ForeignKey("sequences.id"), nullable=True
    )
    status = Column(Enum(CampaignStatus), default=CampaignStatus.draft, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    tenant = relationship("Tenant", back_populates="campaigns")
    sequence = relationship("Sequence", back_populates="campaigns")
    messages = relationship("Message", back_populates="campaign")
    ab_tests = relationship("ABTest", back_populates="campaign")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    channel = Column(Enum(ChannelType), nullable=False)
    direction = Column(Enum(MessageDirection), nullable=False)
    content = Column(Text, nullable=False)
    subject = Column(String, nullable=True)
    status = Column(Enum(MessageStatus), default=MessageStatus.draft, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column("metadata", JSONB, default=dict)

    lead = relationship("Lead", back_populates="messages")
    campaign = relationship("Campaign", back_populates="messages")
    events = relationship("Event", back_populates="message")


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    event_type = Column(Enum(EventType), nullable=False)
    occurred_at = Column(DateTime(timezone=True), default=_utcnow)
    meta = Column("metadata", JSONB, default=dict)

    message = relationship("Message", back_populates="events")


class ABTest(Base):
    __tablename__ = "ab_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(Enum(ABTestStatus), default=ABTestStatus.running, nullable=False)
    variants = Column(JSONB, default=list)
    min_sends_per_variant = Column(Integer, default=100)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    winner_variant_key = Column(String, nullable=True)

    tenant = relationship("Tenant", back_populates="ab_tests")
    campaign = relationship("Campaign", back_populates="ab_tests")
    assignments = relationship("ABTestAssignment", back_populates="test")


class ABTestAssignment(Base):
    __tablename__ = "ab_test_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    test_id = Column(UUID(as_uuid=True), ForeignKey("ab_tests.id"), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    variant_key = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    test = relationship("ABTest", back_populates="assignments")
    lead = relationship("Lead")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name = Column(Enum(PlanName), nullable=False)
    stripe_price_id = Column(String, nullable=True)
    leads_limit = Column(Integer, nullable=False)
    emails_limit = Column(Integer, nullable=False)
    linkedin_limit = Column(Integer, nullable=False)
    campaigns_limit = Column(Integer, nullable=False)
    domains_limit = Column(Integer, nullable=False, default=1)
    price_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.active, nullable=False)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    tenant = relationship("Tenant", back_populates="subscriptions")
    plan = relationship("Plan")


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "period_start", name="uq_usage_tenant_period"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    leads_used = Column(Integer, default=0, nullable=False)
    emails_used = Column(Integer, default=0, nullable=False)
    linkedin_used = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow)

    tenant = relationship("Tenant", back_populates="usage_records")


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    proposed_response = Column(JSONB, nullable=False)
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False)
    reviewer_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    lead = relationship("Lead", back_populates="pending_approvals")
    message = relationship("Message")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    key_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    tenant = relationship("Tenant", back_populates="api_keys")


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    url = Column(String, nullable=False)
    events = Column(JSONB, default=list)
    secret = Column(String, nullable=False)
    template_type = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    is_active = Column(Boolean, default=True, nullable=False)

    tenant = relationship("Tenant", back_populates="webhooks")


class LeadFeedback(Base):
    __tablename__ = "lead_feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    feedback_type = Column(String, nullable=False)
    event_trigger = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    tenant = relationship("Tenant", back_populates="lead_feedbacks")
    lead = relationship("Lead")


class CompetitiveIntel(Base):
    __tablename__ = "competitive_intel"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source = Column(String, nullable=False)
    category = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    competitor_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class TrialStatus(str, enum.Enum):
    active = "active"
    frozen = "frozen"
    converted = "converted"


class Trial(Base):
    __tablename__ = "trials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True)
    status = Column(Enum(TrialStatus), default=TrialStatus.active, nullable=False)
    started_at = Column(DateTime(timezone=True), default=_utcnow)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    leads_used = Column(Integer, default=0)
    emails_used = Column(Integer, default=0)
    converted_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    referrer_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    referred_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    code = Column(String, unique=True, nullable=False)
    reward_applied = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, default=dict)
    status = Column(String, default="pending", nullable=False)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    response_code = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class CostRecord(Base):
    """Tracks per-tenant costs by type (LLM, email, API, proxy)."""

    __tablename__ = "cost_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    cost_type = Column(String, nullable=False)  # "llm", "email", "api", "proxy"
    amount_cents = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

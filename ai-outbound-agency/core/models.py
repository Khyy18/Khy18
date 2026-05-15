import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
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
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    leads = relationship("Lead", back_populates="tenant")
    campaigns = relationship("Campaign", back_populates="tenant")
    sequences = relationship("Sequence", back_populates="tenant")


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

"""Pydantic v2 модели данных AI-агентства."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ServiceType(str, Enum):
    """Типы услуг агентства."""
    COPYWRITING = "copywriting"
    REWRITE = "rewrite"
    SEO = "seo"
    TRANSLATION = "translation"
    SUMMARY = "summary"
    BUSINESS_DOCS = "business_docs"
    CONTENT_PLAN = "content_plan"
    EMAIL_MARKETING = "email_marketing"
    COMPETITOR_ANALYSIS = "competitor_analysis"
    VIDEO_SCRIPT = "video_script"


class OrderStatus(str, Enum):
    """Статусы заказа."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubscriptionTier(str, Enum):
    """Уровни подписки."""
    NONE = "none"
    BASIC = "basic"
    PRO = "pro"


class SubscriptionStatus(str, Enum):
    """Статусы подписки."""
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Client(BaseModel):
    """Модель клиента."""
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    total_spent: float = 0.0
    balance: float = 0.0


class Order(BaseModel):
    """Модель заказа."""
    id: Optional[int] = None
    client_id: int
    service_type: ServiceType
    input_text: str
    output_text: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    price: float = 0.0
    rating: Optional[int] = None


class Payment(BaseModel):
    """Модель платежа."""
    id: Optional[int] = None
    client_id: int
    amount: float
    method: str = "manual"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Subscription(BaseModel):
    """Модель подписки."""
    id: Optional[int] = None
    client_id: int
    tier: SubscriptionTier = SubscriptionTier.NONE
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    started_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    orders_used: int = 0
    yookassa_subscription_id: Optional[str] = None


class Referral(BaseModel):
    """Модель реферала."""
    id: Optional[int] = None
    referrer_id: int
    referred_id: int
    bonus_amount: float = 0.0
    paid: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

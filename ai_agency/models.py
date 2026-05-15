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


class OrderStatus(str, Enum):
    """Статусы заказа."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
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


class Payment(BaseModel):
    """Модель платежа."""
    id: Optional[int] = None
    client_id: int
    amount: float
    method: str = "manual"
    created_at: datetime = Field(default_factory=datetime.utcnow)

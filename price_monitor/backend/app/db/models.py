"""SQLAlchemy async ORM models."""
from __future__ import annotations


from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    is_vip = Column(Boolean, default=False)
    vip_expires_at = Column(DateTime, nullable=True)
    interests = Column(Text, default="[]")
    referral_code = Column(String, unique=True, nullable=True)
    fcm_token = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    badges = relationship("Badge", back_populates="user", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    marketplace = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    url = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    rating = Column(Float, default=0.0)
    reviews_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="product", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="product")
    posts = relationship("Post", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")

class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    old_price = Column(Float, nullable=True)
    discount_percent = Column(Float, nullable=True)
    is_fraud = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="price_history")

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    keyword = Column(String, nullable=False)
    max_price = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="alerts")

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="favorites")
    product = relationship("Product", back_populates="favorites")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    status = Column(String, default="pending")
    plan = Column(String, nullable=True)
    provider = Column(String, nullable=False)
    provider_payment_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="payments")

class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_id = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    converted = Column(Boolean, default=False)

    product = relationship("Product", back_populates="clicks")
    user = relationship("User", back_populates="clicks")
    partner = relationship("Partner", back_populates="clicks")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    channel_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    variant = Column(String, nullable=True)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="posts")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="chat_messages")

class ShortLink(Base):
    __tablename__ = "short_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_id = Column(String, unique=True, nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    affiliate_url = Column(String, nullable=False)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product")
    partner = relationship("Partner", back_populates="short_links")

class PushLog(Base):
    __tablename__ = "push_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    channel_name = Column(String, nullable=False)
    channel_url = Column(String, nullable=True)
    widget_code = Column(String, unique=True, nullable=False)
    commission_percent = Column(Float, default=5.0)
    total_clicks = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)
    balance = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    clicks = relationship("Click", back_populates="partner")
    short_links = relationship("ShortLink", back_populates="partner")

class ArbitrageResult(Base):
    __tablename__ = "arbitrage_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_wb_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_ozon_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    price_wb = Column(Float, nullable=False)
    price_ozon = Column(Float, nullable=False)
    diff_percent = Column(Float, nullable=False)
    match_score = Column(Float, nullable=False)
    found_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product_wb = relationship("Product", foreign_keys=[product_wb_id])
    product_ozon = relationship("Product", foreign_keys=[product_ozon_id])

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    author = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)
    is_fake = Column(Boolean, default=False)
    fake_score = Column(Float, default=0.0)
    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="reviews")

class NicheAnalysis(Base):
    __tablename__ = "niche_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    growth_percent = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=True)
    product_count = Column(Integer, default=0)
    recommendation = Column(Text, nullable=True)
    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class SellerCopy(Base):
    __tablename__ = "seller_copies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    keywords = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product")

class ContentScript(Base):
    __tablename__ = "content_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    script_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product")

class Badge(Base):
    __tablename__ = "badges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    badge_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    earned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="badges")

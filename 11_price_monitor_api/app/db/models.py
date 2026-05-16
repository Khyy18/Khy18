"""SQLAlchemy async ORM models."""

from datetime import datetime

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
    created_at = Column(DateTime, default=datetime.utcnow)

    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


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
    created_at = Column(DateTime, default=datetime.utcnow)

    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="product", cascade="all, delete-orphan")
    clicks = relationship("Click", back_populates="product")
    posts = relationship("Post", back_populates="product", cascade="all, delete-orphan")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    old_price = Column(Float, nullable=True)
    discount_percent = Column(Float, nullable=True)
    is_fraud = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="price_history")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    keyword = Column(String, nullable=False)
    max_price = Column(Float, nullable=True)
    category = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="alerts")


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="favorites")
    product = relationship("Product", back_populates="favorites")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="RUB")
    status = Column(String, default="pending")
    provider = Column(String, nullable=False)
    provider_payment_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="payments")


class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_id = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    converted = Column(Boolean, default=False)

    product = relationship("Product", back_populates="clicks")
    user = relationship("User", back_populates="clicks")


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
    published_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="posts")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_messages")

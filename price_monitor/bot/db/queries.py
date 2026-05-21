"""CRUD-функции для работы с базой данных через SQLAlchemy ORM."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update

from bot.db.session import async_session, close_db as _close_db, engine  # noqa: F401

# Import models from backend via session's sys.path setup
from app.db.models import Alert, Product, PriceHistory, User, Post  # noqa: E402

# Legacy aiosqlite connection for backward-compatible raw SQL in scheduler/tasks.py
import aiosqlite
from bot.config import settings as _settings

_legacy_connection: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get legacy aiosqlite connection for raw SQL queries (backward compat).

    Used by scheduler/tasks.py and other code that still uses raw SQL.
    """
    global _legacy_connection
    if _legacy_connection is None:
        _legacy_connection = await aiosqlite.connect(_settings.db_path)
        _legacy_connection.row_factory = aiosqlite.Row
    return _legacy_connection


async def close_db() -> None:
    """Закрыть engine (пул соединений) и legacy-подключение."""
    global _legacy_connection
    if _legacy_connection is not None:
        await _legacy_connection.close()
        _legacy_connection = None
    await _close_db()


# --- Products ---


async def add_product(
    marketplace: str,
    external_id: str,
    name: str,
    url: str,
    category: str | None = None,
    brand: str | None = None,
) -> int:
    """Добавить товар, вернуть id."""
    async with async_session() as session:
        product = Product(
            marketplace=marketplace,
            external_id=external_id,
            name=name,
            url=url,
            category=category,
            brand=brand,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product.id


async def get_product_by_external_id(marketplace: str, external_id: str) -> dict[str, Any] | None:
    """Найти товар по marketplace + external_id."""
    async with async_session() as session:
        result = await session.execute(
            select(Product).where(
                Product.marketplace == marketplace,
                Product.external_id == external_id,
            )
        )
        product = result.scalar_one_or_none()
        if product is None:
            return None
        return {
            "id": product.id,
            "marketplace": product.marketplace,
            "external_id": product.external_id,
            "name": product.name,
            "category": product.category,
            "brand": product.brand,
            "url": product.url,
            "created_at": product.created_at,
        }


# --- Price History ---


async def add_price_record(
    product_id: int,
    price: float,
    old_price: float | None = None,
    discount_percent: float | None = None,
    is_fraud: bool = False,
) -> int:
    """Добавить запись о цене."""
    async with async_session() as session:
        record = PriceHistory(
            product_id=product_id,
            price=price,
            old_price=old_price,
            discount_percent=discount_percent,
            is_fraud=is_fraud,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def get_price_history(product_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """Получить историю цен товара."""
    async with async_session() as session:
        result = await session.execute(
            select(PriceHistory)
            .where(PriceHistory.product_id == product_id)
            .order_by(PriceHistory.timestamp.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "product_id": r.product_id,
                "price": r.price,
                "old_price": r.old_price,
                "discount_percent": r.discount_percent,
                "is_fraud": r.is_fraud,
                "timestamp": r.timestamp,
            }
            for r in rows
        ]


# --- Users ---


def generate_referral_code() -> str:
    """Генерация уникального реферального кода."""
    return uuid.uuid4().hex[:8]


async def add_user(
    telegram_id: int,
    username: str | None = None,
    referral_code: str | None = None,
    referred_by: str | None = None,
) -> int:
    """Добавить пользователя."""
    if referral_code is None:
        referral_code = generate_referral_code()
    async with async_session() as session:
        # Check if user already exists
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing.id

        user = User(
            telegram_id=telegram_id,
            username=username,
            referral_code=referral_code,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def get_user(telegram_id: int) -> dict[str, Any] | None:
    """Получить пользователя по telegram_id."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        interests = json.loads(user.interests) if user.interests else []
        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "is_vip": user.is_vip,
            "vip_expires_at": user.vip_expires_at,
            "interests": interests,
            "referral_code": user.referral_code,
            "created_at": user.created_at,
        }


async def update_user_vip(telegram_id: int, is_vip: bool, days: int = 30) -> None:
    """Обновить VIP-статус пользователя с установкой даты истечения."""
    async with async_session() as session:
        if is_vip:
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(is_vip=True, vip_expires_at=expires_at)
            )
        else:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(is_vip=False, vip_expires_at=None)
            )
        await session.commit()


async def get_user_by_referral_code(code: str) -> dict[str, Any] | None:
    """Найти пользователя по реферальному коду."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.referral_code == code)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "is_vip": user.is_vip,
            "referral_code": user.referral_code,
            "created_at": user.created_at,
        }


async def get_referral_count(referral_code: str) -> int:
    """Количество пользователей, пришедших по реферальной ссылке."""
    async with async_session() as session:
        # The User model does not have referred_by, so count by referral_code usage
        # For backward compat, we return 0 if the field does not exist
        try:
            result = await session.execute(
                select(func.count()).select_from(User).where(
                    User.referral_code == referral_code
                )
            )
            # Actually referral_code is unique per user, we need to count by referred_by
            # but the backend model doesn't have referred_by column.
            # Return 0 for now as the model lacks this field.
            return 0
        except Exception:
            return 0


# --- Alerts ---


async def add_alert(user_id: int, keyword: str, max_price: float | None = None) -> int:
    """Добавить алерт."""
    async with async_session() as session:
        alert = Alert(
            user_id=user_id,
            keyword=keyword,
            max_price=max_price,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert.id


async def get_user_alerts(user_id: int) -> list[dict[str, Any]]:
    """Получить алерты пользователя."""
    async with async_session() as session:
        result = await session.execute(
            select(Alert).where(Alert.user_id == user_id, Alert.is_active == True)  # noqa: E712
        )
        rows = result.scalars().all()
        return [
            {
                "id": a.id,
                "user_id": a.user_id,
                "keyword": a.keyword,
                "max_price": a.max_price,
                "is_active": a.is_active,
                "created_at": a.created_at,
            }
            for a in rows
        ]


async def delete_alert(alert_id: int) -> None:
    """Деактивировать алерт."""
    async with async_session() as session:
        await session.execute(
            update(Alert).where(Alert.id == alert_id).values(is_active=False)
        )
        await session.commit()


async def get_alert_by_id(alert_id: int) -> dict[str, Any] | None:
    """Получить алерт по ID."""
    async with async_session() as session:
        result = await session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if alert is None:
            return None
        return {
            "id": alert.id,
            "user_id": alert.user_id,
            "keyword": alert.keyword,
            "max_price": alert.max_price,
            "is_active": alert.is_active,
            "created_at": alert.created_at,
        }


async def get_active_alerts_for_keyword(keyword: str) -> list[dict[str, Any]]:
    """Получить все активные алерты.

    Фильтрация по совпадению keyword in product_name делается на уровне Python.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Alert).where(Alert.is_active == True)  # noqa: E712
        )
        rows = result.scalars().all()
        return [
            {
                "id": a.id,
                "user_id": a.user_id,
                "keyword": a.keyword,
                "max_price": a.max_price,
                "is_active": a.is_active,
                "created_at": a.created_at,
            }
            for a in rows
        ]


# --- Seller Monitors ---
# Note: SellerMonitor model is not in the backend models. We keep these
# functions as stubs that return empty data for backward compatibility.


async def add_seller_monitor(
    user_id: int, competitor_url: str, marketplace: str
) -> int:
    """Добавить мониторинг конкурента (stub - model not in backend ORM)."""
    return 0


async def get_user_monitors(user_id: int) -> list[dict[str, Any]]:
    """Получить мониторы конкурентов для пользователя."""
    return []


async def delete_seller_monitor(monitor_id: int) -> None:
    """Удалить мониторинг конкурента."""
    pass


async def get_seller_monitor_by_id(monitor_id: int) -> dict[str, Any] | None:
    """Получить монитор конкурента по ID."""
    return None


async def get_top_referrers(limit: int = 5) -> list[dict[str, Any]]:
    """Получить топ рефереров по количеству приглашений."""
    # Backend model lacks referred_by, return empty for now
    return []


# --- Posts ---


async def add_post(product_id: int, channel_id: int, text: str) -> int:
    """Добавить запись о публикации."""
    async with async_session() as session:
        post = Post(
            product_id=product_id,
            channel_id=channel_id,
            text=text,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id

"""Service layer tests for backend."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceHistory, Product, User
from app.services.gamification import GamificationService
from app.services.niche_detector import NicheDetector
from app.services.payment_service import PaymentService
from app.services.price_forecast import PriceForecastService


class TestGamificationService:
    """Tests for GamificationService."""

    async def test_no_user(self, test_session: AsyncSession):
        """check_and_award_badges with non-existent user returns empty."""
        service = GamificationService()
        result = await service.check_and_award_badges(user_id=99999, db=test_session)
        assert result == []

    async def test_veteran_badge(self, test_session: AsyncSession):
        """User with old created_at gets veteran badge."""
        # Use naive datetime since SQLite stores without timezone
        user = User(
            telegram_id=777777,
            username="olduser",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60),
        )
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        service = GamificationService()
        result = await service.check_and_award_badges(user_id=user.id, db=test_session)

        badge_types = [b.badge_type for b in result]
        assert "veteran_30" in badge_types

    async def test_new_user_no_veteran_badge(self, test_session: AsyncSession):
        """User created recently does not get veteran badge."""
        # Use naive datetime since SQLite stores without timezone
        user = User(
            telegram_id=888888,
            username="newuser",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
        )
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        service = GamificationService()
        result = await service.check_and_award_badges(user_id=user.id, db=test_session)

        badge_types = [b.badge_type for b in result]
        assert "veteran_30" not in badge_types


class TestPriceForecastService:
    """Tests for PriceForecastService."""

    async def test_no_product(self, test_session: AsyncSession):
        """forecast with non-existent product_id returns None."""
        service = PriceForecastService()
        result = await service.forecast(product_id=99999, db=test_session)
        assert result is None

    async def test_insufficient_data(self, test_session: AsyncSession):
        """Product with <3 price points returns stable with low confidence."""
        product = Product(
            marketplace="wb", external_id="12345", name="Test Product"
        )
        test_session.add(product)
        await test_session.commit()
        await test_session.refresh(product)

        # Add only 2 price points (naive datetimes for SQLite)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i, price in enumerate([1000.0, 1050.0]):
            ph = PriceHistory(
                product_id=product.id,
                price=price,
                timestamp=now - timedelta(days=2 - i),
            )
            test_session.add(ph)
        await test_session.commit()

        service = PriceForecastService()
        result = await service.forecast(product_id=product.id, db=test_session)

        assert result is not None
        assert result.trend == "stable"
        assert result.confidence == 0.3

    async def test_falling_prices(self, test_session: AsyncSession):
        """Product with decreasing prices returns falling trend."""
        product = Product(
            marketplace="ozon", external_id="67890", name="Falling Price Product"
        )
        test_session.add(product)
        await test_session.commit()
        await test_session.refresh(product)

        # Add 5 decreasing price points (>10% drop, naive datetimes for SQLite)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        prices = [1000.0, 950.0, 900.0, 850.0, 800.0]
        for i, price in enumerate(prices):
            ph = PriceHistory(
                product_id=product.id,
                price=price,
                timestamp=now - timedelta(days=5 - i),
            )
            test_session.add(ph)
        await test_session.commit()

        service = PriceForecastService()
        result = await service.forecast(product_id=product.id, db=test_session)

        assert result is not None
        assert result.trend == "falling"
        assert result.confidence == 0.7


class TestNicheDetector:
    """Tests for NicheDetector."""

    async def test_empty_db(self, test_session: AsyncSession):
        """analyze with empty DB returns empty list."""
        detector = NicheDetector()
        result = await detector.analyze(db=test_session, days=7)
        assert result == []


class TestPaymentService:
    """Tests for PaymentService."""

    async def test_create_yukassa_payment(self, test_session: AsyncSession):
        """create_yukassa_payment creates a pending payment record."""
        user = User(telegram_id=555555, username="payuser")
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        service = PaymentService()
        result = await service.create_yukassa_payment(
            user_id=user.id,
            amount=299.0,
            plan="month",
            db=test_session,
        )

        assert "payment_id" in result
        assert result["amount"] == 299.0
        # No yukassa credentials in test, so confirmation_url is None
        assert result["confirmation_url"] is None

    async def test_create_telegram_stars_payment(self, test_session: AsyncSession):
        """create_telegram_stars_payment creates a pending stars payment."""
        user = User(telegram_id=666666, username="starsuser")
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        service = PaymentService()
        result = await service.create_telegram_stars_payment(
            user_id=user.id,
            stars_amount=30,
            db=test_session,
        )

        assert "payment_id" in result
        assert result["stars_amount"] == 30
        assert result["vip_days"] == 30

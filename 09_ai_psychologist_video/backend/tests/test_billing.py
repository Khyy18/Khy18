"""Тесты модуля биллинга: пополнение, промокоды, создание сессий."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestTopUp:
    """Тесты пополнения баланса."""

    async def test_topup_increases_balance(self, client: AsyncClient, test_user):
        """Пополнение увеличивает баланс пользователя."""
        user_id, token = test_user

        response = await client.post(
            "/billing/topup",
            json={"amount": 50.00, "source": "demo"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert float(data["new_balance"]) == 150.00  # 100 initial + 50

    async def test_topup_requires_auth(self, client: AsyncClient):
        """Пополнение без авторизации отклоняется."""
        response = await client.post(
            "/billing/topup",
            json={"amount": 50.00, "source": "demo"},
        )
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
class TestPromoCode:
    """Тесты промокодов."""

    async def test_valid_promo_credits_balance(self, client: AsyncClient, test_user, test_promo):
        """Валидный промокод зачисляет бонус."""
        user_id, token = test_user

        response = await client.post(
            "/billing/apply-promo",
            json={"code": "TEST100"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert float(data["new_balance"]) == 200.00  # 100 + 100

    async def test_expired_promo_fails(self, client: AsyncClient, test_user, test_promo):
        """Просроченный промокод отклоняется."""
        _, token = test_user

        response = await client.post(
            "/billing/apply-promo",
            json={"code": "EXPIRED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_maxed_promo_fails(self, client: AsyncClient, test_user, test_promo):
        """Промокод с исчерпанным лимитом отклоняется."""
        _, token = test_user

        response = await client.post(
            "/billing/apply-promo",
            json={"code": "MAXED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400

    async def test_nonexistent_promo_fails(self, client: AsyncClient, test_user):
        """Несуществующий промокод отклоняется."""
        _, token = test_user

        response = await client.post(
            "/billing/apply-promo",
            json={"code": "NONEXISTENT"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestSessionCreation:
    """Тесты создания сессий."""

    async def test_create_session_with_balance(self, client: AsyncClient, test_user):
        """Создание сессии при достаточном балансе."""
        _, token = test_user

        response = await client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert "id" in data

    async def test_create_session_insufficient_balance(self, client: AsyncClient, test_engine):
        """Создание сессии при нулевом балансе отклоняется."""
        import uuid
        from decimal import Decimal
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        from app.models.database import User
        from app.auth.jwt import create_token

        test_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        user_id = str(uuid.uuid4())
        async with test_factory() as session:
            user = User(
                id=user_id,
                telegram_id=999888777,
                username="pooruser",
                balance=Decimal("0.00"),
            )
            session.add(user)
            await session.commit()

        token = create_token(user_id)
        response = await client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 402

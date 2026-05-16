"""Тесты для модуля payments (Telegram Stars)."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiohttp import web

# Перед импортом модуля устанавливаем путь к тестовой БД
_tmp_dir = tempfile.mkdtemp()
os.environ["PAYMENTS_DB_PATH"] = os.path.join(_tmp_dir, "test_payments.db")


from payments import PaymentService
from payments import models
from payments.webhook import setup_routes


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path):
    """Пересоздаём БД для каждого теста."""
    db_path = str(tmp_path / "payments.db")
    with patch.object(models, "DB_PATH", db_path):
        # Патчим _connect чтобы использовать временный путь
        import sqlite3

        def _test_connect():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(models, "_connect", _test_connect):
            models.init_db()
            yield


class TestModels:
    """Тесты для payments/models.py."""

    def test_create_invoice_in_db(self, tmp_path):
        """Создание инвойса записывает корректные поля в БД."""
        invoice_id = models.create_invoice(
            user_tg_id=123456,
            amount_stars=100,
            description="Тестовая оплата",
        )
        assert invoice_id is not None
        assert invoice_id > 0

        invoice = models.get_invoice(invoice_id)
        assert invoice is not None
        assert invoice["user_tg_id"] == 123456
        assert invoice["amount_stars"] == 100
        assert invoice["description"] == "Тестовая оплата"
        assert invoice["status"] == "pending"
        assert invoice["created_at"] is not None
        assert invoice["paid_at"] is None

    def test_mark_paid_updates_status(self, tmp_path):
        """mark_paid меняет статус с 'pending' на 'paid'."""
        invoice_id = models.create_invoice(
            user_tg_id=789,
            amount_stars=50,
            description="Подписка",
        )
        result = models.mark_paid(invoice_id, "charge_abc123")
        assert result is True

        invoice = models.get_invoice(invoice_id)
        assert invoice["status"] == "paid"
        assert invoice["paid_at"] is not None
        assert invoice["telegram_payment_charge_id"] == "charge_abc123"

    def test_mark_paid_already_paid_returns_false(self, tmp_path):
        """Повторная оплата уже оплаченного инвойса возвращает False."""
        invoice_id = models.create_invoice(
            user_tg_id=111, amount_stars=10, description="Тест"
        )
        models.mark_paid(invoice_id, "charge_1")
        result = models.mark_paid(invoice_id, "charge_2")
        assert result is False

    def test_get_user_payments_returns_completed_only(self, tmp_path):
        """get_user_payments возвращает только завершённые платежи."""
        user_id = 555
        # Создаём два инвойса, оплачиваем один
        inv1 = models.create_invoice(user_id, 100, "Оплата 1")
        inv2 = models.create_invoice(user_id, 200, "Оплата 2")
        models.mark_paid(inv1, "charge_a")

        payments = models.get_user_payments(user_id)
        assert len(payments) == 1
        assert payments[0]["invoice_id"] == inv1
        assert payments[0]["amount"] == 100
        assert payments[0]["currency"] == "XTR"

    def test_get_pending_invoice(self, tmp_path):
        """get_pending_invoice возвращает последний неоплаченный инвойс."""
        user_id = 777
        models.create_invoice(user_id, 50, "Первый")
        inv2 = models.create_invoice(user_id, 75, "Второй")

        pending = models.get_pending_invoice(user_id)
        assert pending is not None
        assert pending["id"] == inv2
        assert pending["amount_stars"] == 75


@pytest.mark.asyncio
class TestPaymentService:
    """Тесты для payments/service.py."""

    async def test_create_invoice_link_calls_api(self, tmp_path):
        """create_invoice_link вызывает createInvoiceLink с правильными параметрами."""
        service = PaymentService(token="test_token_123")

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": "https://t.me/invoice/abc"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        result = await service.create_invoice_link(
            session=mock_session,
            user_tg_id=123,
            amount_stars=50,
            title="Подписка Pro",
            description="Ежемесячная подписка",
        )

        assert result == "https://t.me/invoice/abc"
        # Проверяем что вызов API правильный
        call_args = mock_session.post.call_args
        assert "createInvoiceLink" in call_args[0][0]
        assert "bot" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["currency"] == "XTR"
        assert payload["prices"] == [{"label": "Подписка Pro", "amount": 50}]

    async def test_handle_pre_checkout_responds_ok(self, tmp_path):
        """handle_pre_checkout_query отвечает ok=True через API для валидного инвойса."""
        service = PaymentService(token="test_token")

        # Create a pending invoice so validation passes
        invoice_id = models.create_invoice(123, 50, "Тест")

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        result = await service.handle_pre_checkout_query(
            mock_session, "query_123", str(invoice_id)
        )
        assert result is True

        call_args = mock_session.post.call_args
        assert "answerPreCheckoutQuery" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["ok"] is True
        assert payload["pre_checkout_query_id"] == "query_123"

    async def test_handle_successful_payment_records(self, tmp_path):
        """handle_successful_payment помечает инвойс оплаченным."""
        service = PaymentService(token="test_token")

        # Создаём инвойс в БД
        invoice_id = models.create_invoice(999, 100, "Тест")

        update = {
            "message": {
                "from": {"id": 999, "first_name": "TestUser"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 100,
                    "invoice_payload": str(invoice_id),
                    "telegram_payment_charge_id": "charge_xyz",
                }
            }
        }

        result = await service.handle_successful_payment(update)
        assert result == invoice_id

        invoice = models.get_invoice(invoice_id)
        assert invoice["status"] == "paid"
        assert invoice["telegram_payment_charge_id"] == "charge_xyz"


@pytest.mark.asyncio
async def test_webhook_returns_200(tmp_path):
    """Webhook-обработчик возвращает 200 OK на корректный запрос."""
    from aiohttp.test_utils import TestClient, TestServer

    service = PaymentService(token="test_token")
    app = web.Application()
    setup_routes(app, service)

    async with TestClient(TestServer(app)) as client:
        # Пустой update - должен вернуть 200
        resp = await client.post("/webhook/telegram", json={"update_id": 1})
        assert resp.status == 200

        # Update с successful_payment
        resp = await client.post(
            "/webhook/telegram",
            json={
                "update_id": 2,
                "message": {
                    "successful_payment": {
                        "currency": "XTR",
                        "total_amount": 50,
                        "invoice_payload": "999",
                        "telegram_payment_charge_id": "ch_test",
                    }
                },
            },
        )
        assert resp.status == 200

"""Тесты для модуля legal/ (автогенерация договоров-оферт)."""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


@pytest.fixture
def legal_db(tmp_path):
    """Фикстура: временная БД для тестов legal.models."""
    db_path = str(tmp_path / "test_legal.db")
    with patch("legal.models.DB_PATH", db_path):
        from legal import models
        # Патчим _connect чтобы использовать временный путь
        original_connect = models._connect

        def patched_connect():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(models, "_connect", patched_connect):
            models.init_db()
            yield models, db_path


def test_create_offer_record(legal_db):
    """Создание записи оферты в БД с корректным offer_number."""
    models, db_path = legal_db
    offer_id = models.create_offer_record(
        user_tg_id=123456,
        user_name="Иван Тестов",
        amount=5000.0,
        description="Консультация по маркетингу"
    )
    assert offer_id is not None
    assert offer_id > 0

    offer = models.get_offer(offer_id)
    assert offer is not None
    assert offer["user_tg_id"] == 123456
    assert offer["user_name"] == "Иван Тестов"
    assert offer["amount"] == 5000.0
    assert offer["service_description"] == "Консультация по маркетингу"
    assert offer["accepted_at"] is None


def test_offer_number_format(legal_db):
    """offer_number соответствует формату ZC-YYYYMMDD-NNNN."""
    models, _ = legal_db
    offer_id = models.create_offer_record(
        user_tg_id=111,
        user_name="Test",
        amount=1000.0,
        description="Test service"
    )
    offer = models.get_offer(offer_id)
    pattern = r"^ZC-\d{8}-\d{4}$"
    assert re.match(pattern, offer["offer_number"]), \
        f"offer_number '{offer['offer_number']}' не соответствует формату ZC-YYYYMMDD-NNNN"


def test_is_first_payment_true(legal_db):
    """is_first_payment возвращает True если нет акцептованных оферт."""
    models, _ = legal_db
    assert models.is_first_payment(999) is True


def test_is_first_payment_false(legal_db):
    """is_first_payment возвращает False после акцепта оферты."""
    models, _ = legal_db
    offer_id = models.create_offer_record(
        user_tg_id=222,
        user_name="User",
        amount=100.0,
        description="Service"
    )
    models.mark_accepted(offer_id)
    assert models.is_first_payment(222) is False


def test_mark_accepted_updates_record(legal_db):
    """mark_accepted устанавливает accepted_at в записи."""
    models, _ = legal_db
    offer_id = models.create_offer_record(
        user_tg_id=333,
        user_name="Accepted User",
        amount=2000.0,
        description="Design"
    )
    # До акцепта
    offer = models.get_offer(offer_id)
    assert offer["accepted_at"] is None

    # Акцепт
    result = models.mark_accepted(offer_id)
    assert result is True

    # После акцепта
    offer = models.get_offer(offer_id)
    assert offer["accepted_at"] is not None


def test_generate_pdf_returns_bytes(legal_db):
    """OfferGenerator.generate_pdf возвращает непустые bytes."""
    models, _ = legal_db
    from legal.generator import OfferGenerator

    with patch("legal.generator.create_offer_record", models.create_offer_record), \
         patch("legal.generator.get_offer", models.get_offer):
        gen = OfferGenerator()
        pdf_bytes, offer_id = gen.generate_pdf(
            user_tg_id=444,
            user_name="PDF User",
            amount=3000.0,
            service_description="Development"
        )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF файл начинается с %PDF
    assert pdf_bytes[:4] == b"%PDF"


def test_template_has_all_placeholders():
    """OFFER_TEMPLATE содержит все необходимые плейсхолдеры."""
    from legal.template import OFFER_TEMPLATE

    required_placeholders = [
        "{offer_number}",
        "{date}",
        "{user_name}",
        "{amount}",
        "{service_description}",
    ]
    for placeholder in required_placeholders:
        assert placeholder in OFFER_TEMPLATE, \
            f"Плейсхолдер {placeholder} отсутствует в шаблоне"


@pytest.mark.asyncio
async def test_on_first_payment_integration(legal_db):
    """Интеграционный тест: on_first_payment генерирует и отправляет оферту."""
    models, _ = legal_db

    mock_session = AsyncMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_response),
        __aexit__=AsyncMock(return_value=False)
    ))

    with patch("legal.integration.is_first_payment", models.is_first_payment), \
         patch("legal.integration.mark_accepted", models.mark_accepted), \
         patch("legal.generator.create_offer_record", models.create_offer_record), \
         patch("legal.generator.get_offer", models.get_offer), \
         patch("legal.integration.send_offer_to_telegram", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        from legal.integration import on_first_payment
        offer_id = await on_first_payment(
            session=mock_session,
            user_tg_id=555,
            user_name="Integration User",
            amount=7000.0,
            description="Full service"
        )

    assert offer_id is not None
    assert offer_id > 0
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_on_first_payment_skips_second(legal_db):
    """on_first_payment возвращает None для повторного платежа."""
    models, _ = legal_db

    # Создаем и акцептуем первую оферту
    first_id = models.create_offer_record(
        user_tg_id=666,
        user_name="Repeat User",
        amount=1000.0,
        description="First"
    )
    models.mark_accepted(first_id)

    mock_session = AsyncMock()

    with patch("legal.integration.is_first_payment", models.is_first_payment), \
         patch("legal.integration.send_offer_to_telegram", new_callable=AsyncMock) as mock_send:
        from legal.integration import on_first_payment
        result = await on_first_payment(
            session=mock_session,
            user_tg_id=666,
            user_name="Repeat User",
            amount=2000.0,
            description="Second"
        )

    assert result is None
    mock_send.assert_not_called()

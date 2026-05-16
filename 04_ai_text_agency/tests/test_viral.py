"""Тесты реферальной системы (viral/)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from viral import ReferralSystem
from viral import models


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path):
    """Каждый тест использует отдельную временную БД."""
    db_path = str(tmp_path / "test_referrals.db")
    with patch.object(models, "DB_PATH", db_path):
        models.init_db()
        yield


class TestModels:
    """Тесты для viral/models.py."""

    def test_create_referral_code_unique(self):
        """Два вызова для разных пользователей дают разные коды."""
        code1 = models.create_referral_code(111)
        code2 = models.create_referral_code(222)
        assert code1 != code2
        assert len(code1) == 8
        assert len(code2) == 8

    def test_get_existing_code(self):
        """Повторный вызов для того же пользователя возвращает тот же код."""
        code1 = models.create_referral_code(333)
        code2 = models.create_referral_code(333)
        assert code1 == code2

    def test_register_referral_success(self):
        """Успешная регистрация реферала."""
        code = models.create_referral_code(100)
        result = models.register_referral(code, 200)
        assert result is True

    def test_register_referral_duplicate_prevented(self):
        """Один и тот же пользователь не может быть приглашён дважды."""
        code = models.create_referral_code(100)
        result1 = models.register_referral(code, 200)
        assert result1 is True
        # Повторная попытка для того же нового пользователя
        result2 = models.register_referral(code, 200)
        assert result2 is False

    def test_grant_bonus_on_payment(self):
        """Реферер получает бонус при оплате приглашённым."""
        code = models.create_referral_code(100)
        models.register_referral(code, 200)
        bonus = models.grant_bonus_on_payment(200)
        assert bonus is not None
        assert bonus["referrer_tg_id"] == 100
        assert bonus["bonus_type"] == "free_order"
        assert "granted_at" in bonus

    def test_grant_bonus_no_referrer(self):
        """Пользователь без реферера - бонус не начисляется."""
        bonus = models.grant_bonus_on_payment(999)
        assert bonus is None

    def test_get_stats_counts_correctly(self):
        """Статистика корректно считает приглашённых и бонусы."""
        code = models.create_referral_code(100)
        models.register_referral(code, 201)
        models.register_referral(code, 202)
        models.grant_bonus_on_payment(201)

        stats = models.get_referral_stats(100)
        assert stats["invited"] == 2
        assert stats["paid"] == 1
        assert stats["pending"] == 1
        assert stats["bonuses_earned"] == 1


class TestReferralSystem:
    """Тесты для viral/referral.py."""

    def test_generate_link_format(self):
        """ReferralSystem.generate_link возвращает корректный URL."""
        rs = ReferralSystem("test_bot")
        link = rs.generate_link(555)
        assert link.startswith("https://t.me/test_bot?start=ref_")
        # Код должен быть 8 символов после ref_
        code_part = link.split("ref_")[1]
        assert len(code_part) == 8

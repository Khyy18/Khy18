"""Тесты модуля аутентификации."""
import hashlib
import hmac
import json
import time

import pytest

from app.auth.telegram import validate_init_data
from app.auth.jwt import create_token, verify_token


class TestJWT:
    """Тесты JWT создания и верификации."""

    def test_create_and_verify_token(self):
        """Создание и верификация валидного токена."""
        token = create_token("user-123")
        payload = verify_token(token)
        assert payload["sub"] == "user-123"

    def test_invalid_token_raises(self):
        """Невалидный токен вызывает HTTPException."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid.token.here")
        assert exc_info.value.status_code == 401


class TestTelegramValidation:
    """Тесты валидации Telegram initDataRaw."""

    def _make_init_data(self, bot_token: str, user_data: dict, auth_date: int | None = None) -> str:
        """Генерация валидного initDataRaw с правильным HMAC."""
        if auth_date is None:
            auth_date = int(time.time())

        data = {
            "user": json.dumps(user_data),
            "auth_date": str(auth_date),
            "query_id": "test_query_id",
        }

        # Формируем data_check_string
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items())
        )

        # Вычисляем hash
        secret_key = hmac.new(
            key="WebAppData".encode(),
            msg=bot_token.encode(),
            digestmod=hashlib.sha256,
        ).digest()

        computed_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Формируем query string
        parts = [f"{k}={v}" for k, v in data.items()]
        parts.append(f"hash={computed_hash}")
        return "&".join(parts)

    def test_valid_init_data(self):
        """Валидные данные проходят проверку."""
        bot_token = "123456:ABC-DEF"
        user = {"id": 12345, "first_name": "Test", "username": "testuser"}

        init_data_raw = self._make_init_data(bot_token, user)
        result = validate_init_data(init_data_raw, bot_token)

        assert "user" in result
        assert "auth_date" in result

    def test_invalid_hash_rejected(self):
        """Невалидный hash отклоняется."""
        from fastapi import HTTPException

        init_data_raw = "user=%7B%22id%22%3A123%7D&auth_date=9999999999&hash=invalidhash"
        with pytest.raises(HTTPException) as exc_info:
            validate_init_data(init_data_raw, "123456:ABC")
        assert exc_info.value.status_code == 401

    def test_expired_auth_date_rejected(self):
        """Просроченный auth_date отклоняется (>300 секунд)."""
        from fastapi import HTTPException

        bot_token = "123456:ABC-DEF"
        user = {"id": 12345, "first_name": "Test"}
        old_auth_date = int(time.time()) - 600  # 10 minutes ago

        init_data_raw = self._make_init_data(bot_token, user, auth_date=old_auth_date)
        with pytest.raises(HTTPException) as exc_info:
            validate_init_data(init_data_raw, bot_token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_missing_hash_rejected(self):
        """Отсутствие hash отклоняется."""
        from fastapi import HTTPException

        init_data_raw = "user=%7B%22id%22%3A123%7D&auth_date=9999999999"
        with pytest.raises(HTTPException) as exc_info:
            validate_init_data(init_data_raw, "123456:ABC")
        assert exc_info.value.status_code == 401

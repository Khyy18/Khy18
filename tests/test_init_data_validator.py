"""Тесты валидации Telegram WebApp initData."""

import hashlib
import hmac
from urllib.parse import urlencode

import pytest

from payments.init_data_validator import validate_init_data

BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


def _build_valid_init_data(params: dict[str, str], bot_token: str) -> str:
    """Создать валидную строку initData с правильным hash."""
    # Сортируем параметры по ключу
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)

    # Вычисляем secret_key и hash
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Формируем URL-encoded строку с hash
    params_with_hash = {**params, "hash": computed_hash}
    return urlencode(params_with_hash)


class TestValidateInitData:
    """Тесты функции validate_init_data."""

    def test_valid_data(self):
        """Корректные данные проходят валидацию."""
        params = {
            "user": '{"id":123456,"first_name":"Test","last_name":"User"}',
            "auth_date": "1678000000",
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        }
        init_data = _build_valid_init_data(params, BOT_TOKEN)
        assert validate_init_data(init_data, BOT_TOKEN) is True

    def test_tampered_data_fails(self):
        """Изменённые данные не проходят валидацию."""
        params = {
            "user": '{"id":123456,"first_name":"Test"}',
            "auth_date": "1678000000",
        }
        init_data = _build_valid_init_data(params, BOT_TOKEN)
        # Подменяем значение user
        tampered = init_data.replace("Test", "Hacker")
        assert validate_init_data(tampered, BOT_TOKEN) is False

    def test_missing_hash_fails(self):
        """Отсутствие поля hash приводит к неудаче."""
        params = {
            "user": '{"id":123456,"first_name":"Test"}',
            "auth_date": "1678000000",
        }
        # Без hash
        init_data = urlencode(params)
        assert validate_init_data(init_data, BOT_TOKEN) is False

    def test_empty_string_fails(self):
        """Пустая строка не проходит валидацию."""
        assert validate_init_data("", BOT_TOKEN) is False

    def test_empty_bot_token_fails(self):
        """Пустой bot_token не проходит валидацию."""
        params = {
            "user": '{"id":123456}',
            "auth_date": "1678000000",
        }
        init_data = _build_valid_init_data(params, BOT_TOKEN)
        assert validate_init_data(init_data, "") is False

    def test_wrong_bot_token_fails(self):
        """Неправильный bot_token не проходит валидацию."""
        params = {
            "user": '{"id":123456}',
            "auth_date": "1678000000",
        }
        init_data = _build_valid_init_data(params, BOT_TOKEN)
        assert validate_init_data(init_data, "wrong:token") is False

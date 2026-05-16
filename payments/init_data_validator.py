"""Валидация Telegram WebApp initData (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs, urlencode


def validate_init_data(init_data_str: str, bot_token: str) -> bool:
    """Проверяет подлинность initData от Telegram Mini App.

    Алгоритм:
    1. Разбираем URL-encoded строку.
    2. Извлекаем поле 'hash'.
    3. Сортируем оставшиеся параметры по ключу.
    4. Формируем data_check_string = "key=value\\nkey=value..."
    5. secret_key = HMAC-SHA256(key=b"WebAppData", msg=bot_token)
    6. computed_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)
    7. Сравниваем computed_hash с переданным hash.
    """
    if not init_data_str or not bot_token:
        return False

    # Разбор URL-encoded параметров (parse_qs возвращает списки значений)
    try:
        parsed = parse_qs(init_data_str, keep_blank_values=True)
    except Exception:
        return False

    # Извлекаем hash
    hash_list = parsed.pop("hash", None)
    if not hash_list:
        return False
    received_hash = hash_list[0]

    # Формируем data_check_string: сортируем по ключу, берём первое значение
    # Каждый параметр как "key=value", соединяем через \n
    sorted_params = sorted(parsed.items(), key=lambda x: x[0])
    data_check_parts = []
    for key, values in sorted_params:
        # parse_qs возвращает список значений, берём первое
        data_check_parts.append(f"{key}={values[0]}")
    data_check_string = "\n".join(data_check_parts)

    # secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()

    # computed_hash = HMAC-SHA256(key=secret_key, msg=data_check_string)
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hash, received_hash)

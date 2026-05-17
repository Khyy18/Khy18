import hashlib
import hmac
import time
from urllib.parse import parse_qs

from fastapi import HTTPException


def validate_init_data(init_data_raw: str, bot_token: str) -> dict:
    """
    Валидация initDataRaw от Telegram WebApp.

    Алгоритм:
    1. Парсим query string в пары key=value
    2. Извлекаем поле hash из данных
    3. Формируем data_check_string: сортируем оставшиеся поля по алфавиту,
       соединяем через "\\n" в формате "key=value"
    4. Вычисляем secret_key = HMAC-SHA256("WebAppData".encode(), bot_token.encode())
    5. Вычисляем hash = HMAC-SHA256(secret_key, data_check_string.encode())
    6. Сравниваем вычисленный hash с переданным
    7. Проверяем auth_date: не старше 300 секунд
    """
    parsed = parse_qs(init_data_raw, keep_blank_values=True)

    # parse_qs возвращает списки значений, берем первый элемент
    data = {k: v[0] for k, v in parsed.items()}

    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in init data")

    # Формируем строку для проверки: сортированные пары key=value через \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items())
    )

    # Ключ = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        key="WebAppData".encode(),
        msg=bot_token.encode(),
        digestmod=hashlib.sha256,
    ).digest()

    # Вычисляем хеш данных
    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid init data signature")

    # Проверяем auth_date: не старше 300 секунд
    auth_date_str = data.get("auth_date")
    if not auth_date_str:
        raise HTTPException(status_code=401, detail="Missing auth_date in init data")

    try:
        auth_date = int(auth_date_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid auth_date format")

    current_time = int(time.time())
    if current_time - auth_date > 300:
        raise HTTPException(status_code=401, detail="Init data expired")

    return data

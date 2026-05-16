"""Middleware для валидации Telegram initData и проверки ролей."""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ai_office.core.config import settings
from ai_office.core.permissions import UserRole, get_user_role

logger = logging.getLogger(__name__)


class TelegramAuthMiddleware(BaseHTTPMiddleware):
    """Валидация Telegram Mini App initData через HMAC-SHA256 + проверка ролей."""

    SKIP_PATHS = {"/api/health", "/api/ws", "/api/metrics", "/docs", "/openapi.json"}
    SKIP_PREFIXES = ("/api/public/",)

    # Методы записи, запрещённые для viewer
    WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        # Пропускаем аутентификацию в dev-режиме
        if settings.skip_telegram_auth:
            request.state.user_role = UserRole.OWNER.value
            return await call_next(request)

        # Пропускаем не-API маршруты и исключенные пути
        path = request.url.path
        if not path.startswith("/api/") or path in self.SKIP_PATHS:
            return await call_next(request)

        # Пропускаем публичные маршруты (доступны без аутентификации)
        if any(path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return await call_next(request)

        # Извлекаем initData из заголовка или query-параметра
        init_data = (
            request.headers.get("X-Telegram-Init-Data")
            or request.query_params.get("initData")
        )
        if not init_data:
            return JSONResponse(
                status_code=401, content={"detail": "Missing initData"}
            )

        if not self.validate_init_data(init_data):
            return JSONResponse(
                status_code=401, content={"detail": "Invalid initData"}
            )

        # Извлекаем telegram_id из initData и проверяем роль
        telegram_id = self._extract_telegram_id(init_data)
        if telegram_id:
            try:
                user_role = await get_user_role(telegram_id)
                role_value = user_role.value if user_role else UserRole.VIEWER.value
            except Exception:
                role_value = UserRole.VIEWER.value
            request.state.user_role = role_value

            # Viewer не может выполнять операции записи
            if role_value == UserRole.VIEWER.value and request.method in self.WRITE_METHODS:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Недостаточно прав для данной операции"},
                )
        else:
            request.state.user_role = UserRole.VIEWER.value

        return await call_next(request)

    @staticmethod
    def _extract_telegram_id(init_data: str) -> int | None:
        """Извлечь telegram_id из initData."""
        try:
            parsed = dict(
                pair.split("=", 1) for pair in unquote(init_data).split("&")
            )
            user_str = parsed.get("user")
            if user_str:
                user_data = json.loads(user_str)
                return user_data.get("id")
        except Exception:
            pass
        return None

    @staticmethod
    def validate_init_data(init_data: str) -> bool:
        """Валидация Telegram Web App initData через HMAC-SHA256."""
        try:
            parsed = dict(
                pair.split("=", 1) for pair in unquote(init_data).split("&")
            )
            received_hash = parsed.pop("hash", None)
            if not received_hash:
                return False

            # Проверка свежести auth_date (не старше 5 минут)
            auth_date = parsed.get("auth_date")
            if auth_date:
                try:
                    if time.time() - int(auth_date) > 300:  # 5 minutes
                        return False
                except (ValueError, TypeError):
                    pass

            # Сортировка и формирование data-check-string
            data_check_string = "\n".join(
                f"{k}={v}" for k, v in sorted(parsed.items())
            )

            # Вычисление HMAC
            secret_key = hmac.new(
                b"WebAppData",
                settings.telegram_bot_token.encode(),
                hashlib.sha256,
            ).digest()
            computed_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(computed_hash, received_hash)
        except Exception:
            return False

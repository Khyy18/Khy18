"""Middleware для валидации Telegram initData."""

import hashlib
import hmac
import time
from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ai_office.core.config import settings


class TelegramAuthMiddleware(BaseHTTPMiddleware):
    """Валидация Telegram Mini App initData через HMAC-SHA256."""

    SKIP_PATHS = {"/api/health", "/api/ws", "/docs", "/openapi.json", "/api/billing/plans", "/api/billing/webhook"}
    SKIP_PREFIXES = ("/api/auth",)

    async def dispatch(self, request: Request, call_next):
        # Пропускаем аутентификацию в dev-режиме
        if settings.skip_telegram_auth:
            return await call_next(request)

        # Пропускаем не-API маршруты и исключенные пути
        path = request.url.path
        if not path.startswith("/api/") or path in self.SKIP_PATHS:
            return await call_next(request)

        # Skip auth prefixes
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

        return await call_next(request)

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

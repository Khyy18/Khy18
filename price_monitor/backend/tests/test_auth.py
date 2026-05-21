"""Tests for authentication middleware (JWT and Telegram initData)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from app.config import settings
from app.middleware.auth import (
    _AUTH_DATE_MAX_AGE,
    create_access_token,
    verify_telegram_init_data,
    verify_token,
)


class TestCreateAccessToken:
    """Tests for create_access_token."""

    def test_returns_string(self):
        """create_access_token returns a non-empty string."""
        token = create_access_token({"sub": "42"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_three_parts(self):
        """JWT has header.payload.signature structure."""
        token = create_access_token({"sub": "1"})
        parts = token.split(".")
        assert len(parts) == 3


class TestVerifyToken:
    """Tests for verify_token."""

    def test_valid_token_returns_payload(self):
        """verify_token with a valid token returns dict with 'sub' key."""
        token = create_access_token({"sub": "99"})
        payload = verify_token(token)
        assert payload["sub"] == "99"
        assert "exp" in payload

    def test_invalid_token_raises_401(self):
        """verify_token with garbage token raises HTTPException 401."""
        with pytest.raises(HTTPException) as exc_info:
            verify_token("invalid.token.value")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        """verify_token with expired token raises HTTPException 401."""
        from jose import jwt as jose_jwt

        # Create a token already expired
        payload = {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jose_jwt.encode(
            payload, settings.secret_key, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        """Token signed with wrong secret is rejected."""
        from jose import jwt as jose_jwt

        payload = {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        bad_token = jose_jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            verify_token(bad_token)
        assert exc_info.value.status_code == 401


class TestVerifyTelegramInitData:
    """Tests for verify_telegram_init_data."""

    @staticmethod
    def _build_valid_init_data(bot_token: str, user_data: dict, auth_date: int | None = None) -> str:
        """Helper to construct a valid Telegram initData string with correct HMAC."""
        if auth_date is None:
            auth_date = int(time.time())

        user_json = json.dumps(user_data, separators=(",", ":"))
        params = {
            "auth_date": str(auth_date),
            "user": user_json,
        }

        # Build data-check-string (sorted keys, newline separated)
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        # Compute HMAC
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        params["hash"] = computed_hash
        return urlencode(params)

    def test_valid_hmac_returns_user(self):
        """verify_telegram_init_data with valid HMAC returns user dict."""
        bot_token = "1234567890:ABCDefGHIJKlmnoPQRSTuvwxyz"
        user_data = {"id": 123456, "first_name": "Test", "username": "testuser"}

        init_data = self._build_valid_init_data(bot_token, user_data)

        with patch.object(settings, "telegram_bot_token", bot_token):
            result = verify_telegram_init_data(init_data)

        assert result is not None
        assert result["id"] == 123456
        assert result["username"] == "testuser"

    def test_invalid_hash_returns_none(self):
        """verify_telegram_init_data with wrong hash returns None."""
        bot_token = "1234567890:ABCDefGHIJKlmnoPQRSTuvwxyz"
        user_json = json.dumps({"id": 123, "username": "x"}, separators=(",", ":"))
        init_data = urlencode({
            "auth_date": str(int(time.time())),
            "user": user_json,
            "hash": "0" * 64,  # invalid hash
        })

        with patch.object(settings, "telegram_bot_token", bot_token):
            result = verify_telegram_init_data(init_data)

        assert result is None

    def test_expired_auth_date_returns_none(self):
        """verify_telegram_init_data with auth_date older than 24h returns None."""
        bot_token = "1234567890:ABCDefGHIJKlmnoPQRSTuvwxyz"
        user_data = {"id": 999, "username": "expired_user"}
        old_auth_date = int(time.time()) - _AUTH_DATE_MAX_AGE - 100

        init_data = self._build_valid_init_data(bot_token, user_data, auth_date=old_auth_date)

        with patch.object(settings, "telegram_bot_token", bot_token):
            result = verify_telegram_init_data(init_data)

        assert result is None

    def test_no_bot_token_dev_mode_parses_user(self):
        """Without bot token (dev mode), user data is parsed directly from URL params."""
        user_data = {"id": 42, "username": "dev_user"}
        user_json = json.dumps(user_data, separators=(",", ":"))
        init_data = urlencode({"user": user_json})

        with patch.object(settings, "telegram_bot_token", ""):
            result = verify_telegram_init_data(init_data)

        assert result is not None
        assert result["id"] == 42
        assert result["username"] == "dev_user"

    def test_no_bot_token_no_user_returns_none(self):
        """Without bot token and no user param, returns None."""
        init_data = "query_id=AAHdF6IQAAAAAN0XohDhrOrc"

        with patch.object(settings, "telegram_bot_token", ""):
            result = verify_telegram_init_data(init_data)

        assert result is None

    def test_missing_hash_returns_none(self):
        """init_data without hash field returns None."""
        bot_token = "1234567890:ABCDefGHIJKlmnoPQRSTuvwxyz"
        user_json = json.dumps({"id": 1}, separators=(",", ":"))
        init_data = urlencode({"auth_date": str(int(time.time())), "user": user_json})

        with patch.object(settings, "telegram_bot_token", bot_token):
            result = verify_telegram_init_data(init_data)

        assert result is None

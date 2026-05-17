"""Tests for natal chart calculation, prompts, billing, and models."""

import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote, urlencode

import pytest

from app.astro import calculate_natal_chart, _degree_to_sign, _calculate_aspect
from app.billing import BillingManager
from app.models import (
    BirthData,
    NatalChart,
    UserSession,
    BillingEvent,
    SessionStartRequest,
    BalanceTopupRequest,
    CallStatus,
)
from app.prompts import SYSTEM_PROMPT, build_session_prompt


class TestNatalChart:
    """Tests for natal chart calculation."""

    def test_calculate_natal_chart_returns_natal_chart(self):
        """Test that calculate_natal_chart returns a valid NatalChart."""
        birth_data = BirthData(
            date="1990-06-15",
            time="14:30",
            lat=55.7558,
            lon=37.6173,
            city="Moscow",
        )
        result = calculate_natal_chart(birth_data)
        assert isinstance(result, NatalChart)

    def test_natal_chart_has_all_planets(self):
        """Test that all 10 planets are calculated."""
        birth_data = BirthData(
            date="1990-06-15",
            time="14:30",
            lat=55.7558,
            lon=37.6173,
            city="Moscow",
        )
        result = calculate_natal_chart(birth_data)
        expected_planets = [
            "Sun", "Moon", "Mercury", "Venus", "Mars",
            "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
        ]
        for planet in expected_planets:
            assert planet in result.planets
            assert "sign" in result.planets[planet]
            assert "degree" in result.planets[planet]
            assert "house" in result.planets[planet]

    def test_natal_chart_has_houses(self):
        """Test that all 12 houses are calculated."""
        birth_data = BirthData(
            date="1990-06-15",
            time="14:30",
            lat=55.7558,
            lon=37.6173,
            city="Moscow",
        )
        result = calculate_natal_chart(birth_data)
        assert len(result.houses) == 12
        for i in range(1, 13):
            assert str(i) in result.houses

    def test_natal_chart_has_ascendant_and_mc(self):
        """Test that ascendant and MC are calculated."""
        birth_data = BirthData(
            date="1990-06-15",
            time="14:30",
            lat=55.7558,
            lon=37.6173,
            city="Moscow",
        )
        result = calculate_natal_chart(birth_data)
        assert result.ascendant != ""
        assert result.mc != ""
        assert result.ascendant in [
            "Aries", "Taurus", "Gemini", "Cancer",
            "Leo", "Virgo", "Libra", "Scorpio",
            "Sagittarius", "Capricorn", "Aquarius", "Pisces",
        ]

    def test_natal_chart_has_aspects(self):
        """Test that aspects are calculated."""
        birth_data = BirthData(
            date="1990-06-15",
            time="14:30",
            lat=55.7558,
            lon=37.6173,
            city="Moscow",
        )
        result = calculate_natal_chart(birth_data)
        assert len(result.aspects) > 0
        for aspect in result.aspects:
            assert "planet1" in aspect
            assert "planet2" in aspect
            assert "aspect_type" in aspect
            assert "orb" in aspect

    def test_known_sun_position(self):
        """Test Sun position for a known date (June 15, 1990 should be Gemini)."""
        birth_data = BirthData(
            date="1990-06-15",
            time="12:00",
            lat=0.0,
            lon=0.0,
            city="Equator",
        )
        result = calculate_natal_chart(birth_data)
        assert result.planets["Sun"]["sign"] == "Gemini"

    def test_degree_to_sign(self):
        """Test degree to sign conversion."""
        assert _degree_to_sign(0.0) == "Aries"
        assert _degree_to_sign(30.0) == "Taurus"
        assert _degree_to_sign(60.0) == "Gemini"
        assert _degree_to_sign(90.0) == "Cancer"
        assert _degree_to_sign(120.0) == "Leo"
        assert _degree_to_sign(150.0) == "Virgo"
        assert _degree_to_sign(180.0) == "Libra"
        assert _degree_to_sign(210.0) == "Scorpio"
        assert _degree_to_sign(240.0) == "Sagittarius"
        assert _degree_to_sign(270.0) == "Capricorn"
        assert _degree_to_sign(300.0) == "Aquarius"
        assert _degree_to_sign(330.0) == "Pisces"

    def test_calculate_aspect_conjunction(self):
        """Test conjunction aspect detection."""
        result = _calculate_aspect(10.0, 12.0)
        assert result is not None
        assert result[0] == "Conjunction"

    def test_calculate_aspect_opposition(self):
        """Test opposition aspect detection."""
        result = _calculate_aspect(10.0, 190.0)
        assert result is not None
        assert result[0] == "Opposition"

    def test_calculate_aspect_trine(self):
        """Test trine aspect detection."""
        result = _calculate_aspect(10.0, 130.0)
        assert result is not None
        assert result[0] == "Trine"

    def test_calculate_aspect_no_aspect(self):
        """Test no aspect when angles don't match."""
        result = _calculate_aspect(10.0, 55.0)
        assert result is None


class TestPrompts:
    """Tests for prompt system."""

    def test_system_prompt_exists_and_in_russian(self):
        """Test that system prompt is defined and contains Russian text."""
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 100
        assert "Стелла" in SYSTEM_PROMPT

    def test_system_prompt_contains_rules(self):
        """Test that system prompt contains formatting rules."""
        assert "1-3" in SYSTEM_PROMPT
        assert "НИКОГДА" in SYSTEM_PROMPT or "никогда" in SYSTEM_PROMPT

    def test_build_session_prompt_includes_system_prompt(self):
        """Test that build_session_prompt includes the base system prompt."""
        chart = NatalChart(
            planets={"Sun": {"sign": "Gemini", "degree": "23.45", "house": "10"}},
            houses={"1": "Libra"},
            ascendant="Libra",
            mc="Cancer",
            aspects=[],
        )
        result = build_session_prompt(chart)
        assert SYSTEM_PROMPT in result

    def test_build_session_prompt_includes_chart_data(self):
        """Test that build_session_prompt includes natal chart data."""
        chart = NatalChart(
            planets={
                "Sun": {"sign": "Gemini", "degree": "23.45", "house": "10"},
                "Moon": {"sign": "Scorpio", "degree": "5.12", "house": "2"},
            },
            houses={"1": "Libra"},
            ascendant="Libra",
            mc="Cancer",
            aspects=[{
                "planet1": "Sun",
                "planet2": "Moon",
                "aspect_type": "Trine",
                "orb": "2.5",
            }],
        )
        result = build_session_prompt(chart)
        assert "Libra" in result
        assert "Gemini" in result
        assert "Scorpio" in result
        assert "Cancer" in result
        assert "Trine" in result


class TestBilling:
    """Tests for billing logic with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis._store = {}

        async def mock_get(key):
            return redis._store.get(key)

        async def mock_set(key, value):
            redis._store[key] = value

        async def mock_eval(script, numkeys, *args):
            """Simulate Lua script for atomic deduct."""
            key = args[0]
            cost = int(args[1])
            current = int(redis._store.get(key) or "0")
            if current < cost:
                return [0, current]
            new_balance = current - cost
            redis._store[key] = str(new_balance)
            return [1, new_balance]

        redis.get = AsyncMock(side_effect=mock_get)
        redis.set = AsyncMock(side_effect=mock_set)
        redis.eval = AsyncMock(side_effect=mock_eval)
        return redis

    @pytest.fixture
    def billing(self, mock_redis):
        """Create a BillingManager with mock Redis."""
        manager = BillingManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_get_balance_default_zero(self, billing):
        """Test that balance returns 0 for unknown user."""
        balance = await billing.get_balance("unknown_user")
        assert balance == 0

    @pytest.mark.asyncio
    async def test_set_and_get_balance(self, billing):
        """Test setting and getting balance."""
        await billing.set_balance("user1", 100)
        balance = await billing.get_balance("user1")
        assert balance == 100

    @pytest.mark.asyncio
    async def test_deduct_minute_success(self, billing):
        """Test successful minute deduction."""
        await billing.set_balance("user1", 100)
        success, remaining = await billing.deduct_minute("user1", 10)
        assert success is True
        assert remaining == 90

    @pytest.mark.asyncio
    async def test_deduct_minute_insufficient_balance(self, billing):
        """Test deduction when balance is insufficient."""
        await billing.set_balance("user1", 5)
        success, remaining = await billing.deduct_minute("user1", 10)
        assert success is False
        assert remaining == 5

    @pytest.mark.asyncio
    async def test_deduct_minute_exact_balance(self, billing):
        """Test deduction when balance equals cost exactly."""
        await billing.set_balance("user1", 10)
        success, remaining = await billing.deduct_minute("user1", 10)
        assert success is True
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_topup_balance(self, billing):
        """Test balance top-up."""
        await billing.set_balance("user1", 50)
        new_balance = await billing.topup_balance("user1", 30)
        assert new_balance == 80

    @pytest.mark.asyncio
    async def test_get_balance_no_redis(self):
        """Test that billing returns 0 without Redis."""
        manager = BillingManager(redis_client=None)
        balance = await manager.get_balance("user1")
        assert balance == 0


class TestModels:
    """Tests for Pydantic models validation."""

    def test_birth_data_valid(self):
        """Test valid BirthData creation."""
        data = BirthData(
            date="1990-06-15",
            time="14:30",
            lat=55.7558,
            lon=37.6173,
            city="Moscow",
        )
        assert data.date == "1990-06-15"
        assert data.lat == 55.7558

    def test_birth_data_missing_fields(self):
        """Test that BirthData requires all fields."""
        with pytest.raises(Exception):
            BirthData(date="1990-06-15")

    def test_session_start_request(self):
        """Test SessionStartRequest validation."""
        req = SessionStartRequest(
            user_id="user123",
            birth_data=BirthData(
                date="1990-06-15",
                time="14:30",
                lat=55.7558,
                lon=37.6173,
                city="Moscow",
            ),
            balance=200,
        )
        assert req.user_id == "user123"
        assert req.balance == 200

    def test_balance_topup_request_positive(self):
        """Test that BalanceTopupRequest requires positive amount."""
        with pytest.raises(Exception):
            BalanceTopupRequest(user_id="user1", amount=-10)

    def test_call_status_enum(self):
        """Test CallStatus enum values."""
        assert CallStatus.IDLE == "idle"
        assert CallStatus.ACTIVE == "active"
        assert CallStatus.ENDED == "ended"
        assert CallStatus.CONNECTING == "connecting"

    def test_natal_chart_model(self):
        """Test NatalChart model creation."""
        chart = NatalChart(
            planets={"Sun": {"sign": "Gemini", "degree": "23.45", "house": "10"}},
            houses={"1": "Libra"},
            ascendant="Libra",
            mc="Cancer",
            aspects=[],
        )
        assert chart.ascendant == "Libra"
        assert chart.planets["Sun"]["sign"] == "Gemini"

    def test_user_session_defaults(self):
        """Test UserSession default values."""
        session = UserSession(
            user_id="user1",
            session_id="sess1",
        )
        assert session.balance == 0
        assert session.status == CallStatus.IDLE
        assert session.natal_chart is None


class TestTelegramAuth:
    """Tests for Telegram initData HMAC validation."""

    def _make_init_data(self, bot_token: str, user_data: dict) -> str:
        """Helper to create a valid Telegram initData string with correct HMAC."""
        user_json = json.dumps(user_data, separators=(",", ":"))
        params = {
            "user": user_json,
            "auth_date": str(int(time.time())),
            "query_id": "test_query_123",
        }
        # Build data-check-string
        data_check_pairs = []
        for key in sorted(params.keys()):
            data_check_pairs.append(f"{key}={params[key]}")
        data_check_string = "\n".join(data_check_pairs)

        # Compute HMAC
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        params["hash"] = computed_hash
        return urlencode(params)

    @patch("app.telegram_auth.settings")
    def test_valid_hmac(self, mock_settings):
        """Test that valid HMAC passes validation."""
        from app.telegram_auth import validate_init_data

        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        mock_settings.telegram_bot_token = bot_token
        user_data = {"id": 12345, "first_name": "Test"}
        init_data = self._make_init_data(bot_token, user_data)

        result = validate_init_data(init_data)
        assert result == "12345"

    @patch("app.telegram_auth.settings")
    def test_invalid_hmac(self, mock_settings):
        """Test that invalid HMAC raises HTTPException."""
        from app.telegram_auth import validate_init_data

        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        mock_settings.telegram_bot_token = bot_token
        user_data = {"id": 12345, "first_name": "Test"}
        init_data = self._make_init_data(bot_token, user_data)

        # Tamper with the data
        init_data = init_data.replace("test_query_123", "tampered_query")

        from fastapi import HTTPException as FastAPIHTTPException

        with pytest.raises(FastAPIHTTPException) as exc_info:
            validate_init_data(init_data)
        assert exc_info.value.status_code == 403

    @patch("app.telegram_auth.settings")
    def test_missing_token_fallback(self, mock_settings):
        """Test that missing bot token enables dev mode fallback."""
        from app.telegram_auth import validate_init_data

        mock_settings.telegram_bot_token = ""
        user_data = {"id": 99999, "first_name": "DevUser"}
        user_json = json.dumps(user_data, separators=(",", ":"))
        init_data = urlencode({"user": user_json, "auth_date": "1234567890"})

        result = validate_init_data(init_data)
        assert result == "99999"

    @patch("app.telegram_auth.settings")
    def test_missing_token_no_user_data(self, mock_settings):
        """Test dev fallback with no user data returns dev_user."""
        from app.telegram_auth import validate_init_data

        mock_settings.telegram_bot_token = ""
        init_data = urlencode({"auth_date": "1234567890"})

        result = validate_init_data(init_data)
        assert result == "dev_user"


class TestSessionStore:
    """Tests for Redis session store with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client for session store."""
        redis = AsyncMock()
        redis._store = {}

        async def mock_get(key):
            return redis._store.get(key)

        async def mock_set(key, value, ex=None):
            redis._store[key] = value

        async def mock_delete(key):
            redis._store.pop(key, None)

        redis.get = AsyncMock(side_effect=mock_get)
        redis.set = AsyncMock(side_effect=mock_set)
        redis.delete = AsyncMock(side_effect=mock_delete)
        return redis

    @pytest.fixture
    def store(self, mock_redis):
        """Create a RedisSessionStore with mock Redis."""
        from app.session_store import RedisSessionStore

        return RedisSessionStore(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_save_and_get_session(self, store):
        """Test saving and retrieving a session."""
        session = UserSession(
            user_id="user1",
            session_id="sess1",
            balance=100,
            status=CallStatus.ACTIVE,
        )
        await store.save_session(session)
        retrieved = await store.get_session("sess1")
        assert retrieved is not None
        assert retrieved.user_id == "user1"
        assert retrieved.session_id == "sess1"
        assert retrieved.balance == 100
        assert retrieved.status == CallStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, store):
        """Test retrieving a session that does not exist."""
        result = await store.get_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_session(self, store):
        """Test deleting a session."""
        session = UserSession(
            user_id="user1",
            session_id="sess1",
            balance=50,
        )
        await store.save_session(session)
        await store.delete_session("sess1")
        result = await store.get_session("sess1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get_history(self, store):
        """Test saving and retrieving conversation history."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        await store.save_history("sess1", history)
        result = await store.get_history("sess1")
        assert result == history

    @pytest.mark.asyncio
    async def test_get_empty_history(self, store):
        """Test retrieving history for non-existent session."""
        result = await store.get_history("nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_save_and_get_pipeline_context(self, store):
        """Test saving and retrieving pipeline context."""
        prompt = "You are an astrologer named Stella."
        await store.save_pipeline_context("sess1", prompt)
        result = await store.get_pipeline_context("sess1")
        assert result == prompt

    @pytest.mark.asyncio
    async def test_save_and_get_token(self, store):
        """Test saving and retrieving auth token."""
        await store.save_token("sess1", "abc123token")
        result = await store.get_token("sess1")
        assert result == "abc123token"

    @pytest.mark.asyncio
    async def test_delete_token(self, store):
        """Test deleting auth token."""
        await store.save_token("sess1", "abc123token")
        await store.delete_token("sess1")
        result = await store.get_token("sess1")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_redis_returns_none(self):
        """Test that store with no Redis returns None/empty gracefully."""
        from app.session_store import RedisSessionStore

        store = RedisSessionStore(redis_client=None)
        assert await store.get_session("sess1") is None
        assert await store.get_history("sess1") == []
        assert await store.get_pipeline_context("sess1") is None
        assert await store.get_token("sess1") is None
        # These should not raise
        await store.save_session(
            UserSession(user_id="u", session_id="s")
        )
        await store.delete_session("sess1")


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    def test_circuit_starts_closed(self):
        """Test that circuit breaker starts in closed state."""
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test")
        assert cb.state == "closed"
        assert not cb.is_open()

    def test_circuit_opens_after_threshold(self):
        """Test that circuit opens after enough failures."""
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=30.0)
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_open()
        cb.record_failure()
        assert cb.is_open()
        assert cb.state == "open"

    def test_circuit_resets_on_success(self):
        """Test that a success resets the failure counter."""
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"

    def test_circuit_half_open_after_timeout(self):
        """Test that circuit enters half-open after recovery timeout."""
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()

        # Wait for recovery timeout
        time.sleep(0.15)
        assert not cb.is_open()
        assert cb.state == "half-open"

    @pytest.mark.asyncio
    async def test_decorator_returns_fallback_on_failure(self):
        """Test that the decorator returns fallback when function fails."""
        from app.circuit_breaker import CircuitBreaker, with_circuit_breaker

        cb = CircuitBreaker("test_decorator", failure_threshold=5)
        fallback_value = "fallback_result"

        @with_circuit_breaker(cb, fallback_value)
        async def failing_function():
            raise ValueError("test error")

        result = await failing_function()
        assert result == fallback_value

    @pytest.mark.asyncio
    async def test_decorator_returns_result_on_success(self):
        """Test that the decorator returns normal result on success."""
        from app.circuit_breaker import CircuitBreaker, with_circuit_breaker

        cb = CircuitBreaker("test_success", failure_threshold=5)
        fallback_value = "fallback_result"

        @with_circuit_breaker(cb, fallback_value)
        async def success_function():
            return "real_result"

        result = await success_function()
        assert result == "real_result"

    @pytest.mark.asyncio
    async def test_decorator_returns_fallback_when_circuit_open(self):
        """Test that the decorator returns fallback immediately when circuit is open."""
        from app.circuit_breaker import CircuitBreaker, with_circuit_breaker

        cb = CircuitBreaker("test_open", failure_threshold=2, recovery_timeout=60.0)
        fallback_value = "fallback"

        call_count = 0

        @with_circuit_breaker(cb, fallback_value)
        async def tracked_function():
            nonlocal call_count
            call_count += 1
            return "real"

        # Open the circuit manually
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()

        result = await tracked_function()
        assert result == "fallback"
        # Function should not have been called
        assert call_count == 0

    def test_circuit_reset(self):
        """Test explicit circuit reset."""
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test_reset", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open()

        cb.reset()
        assert cb.state == "closed"
        assert cb.failure_count == 0
        assert not cb.is_open()

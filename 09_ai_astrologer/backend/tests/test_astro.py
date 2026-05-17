"""Tests for natal chart calculation, prompts, billing, and models."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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

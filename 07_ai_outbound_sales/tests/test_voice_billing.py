"""Tests for Voice AI add-on billing logic."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from core.models import VoiceAddon, VoiceAddonPlan
from integrations.voice_usage import (
    VOICE_PLANS,
    NoActiveVoiceAddonError,
    check_and_increment_usage,
    get_active_voice_addon,
    get_voice_usage,
    reset_period_usage,
)
from tests.conftest import (
    make_plan,
    make_subscription,
    make_tenant,
    make_user,
    make_voice_addon,
)


# ---------- Voice Usage Service Tests ----------


async def test_get_active_voice_addon_returns_active(async_session):
    """Test fetching active voice addon for tenant."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = make_voice_addon(tenant_id=tenant.id)
    async_session.add(addon)
    await async_session.flush()

    result = await get_active_voice_addon(async_session, tenant.id)
    assert result is not None
    assert result.id == addon.id
    assert result.is_active is True


async def test_get_active_voice_addon_returns_none_when_inactive(async_session):
    """Test that inactive addons are not returned."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = make_voice_addon(tenant_id=tenant.id, is_active=False)
    async_session.add(addon)
    await async_session.flush()

    result = await get_active_voice_addon(async_session, tenant.id)
    assert result is None


async def test_get_active_voice_addon_returns_none_when_no_addon(async_session):
    """Test returns None when no addon exists."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    result = await get_active_voice_addon(async_session, tenant.id)
    assert result is None


async def test_check_and_increment_usage_success(async_session):
    """Test successful usage increment within limit."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = make_voice_addon(tenant_id=tenant.id, calls_limit=50, calls_used_this_period=10)
    async_session.add(addon)
    await async_session.flush()

    result = await check_and_increment_usage(async_session, tenant.id)
    assert result["allowed"] is True
    assert result["calls_used"] == 11
    assert result["calls_limit"] == 50
    assert result["is_overage"] is False
    assert result["overage_calls"] == 0
    assert result["overage_cost_cents"] == 0


async def test_check_and_increment_usage_overage(async_session):
    """Test usage increment when at limit (overage)."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = make_voice_addon(
        tenant_id=tenant.id, calls_limit=50, calls_used_this_period=50
    )
    async_session.add(addon)
    await async_session.flush()

    result = await check_and_increment_usage(async_session, tenant.id)
    assert result["allowed"] is True
    assert result["calls_used"] == 51
    assert result["is_overage"] is True
    assert result["overage_calls"] == 1
    assert result["overage_cost_cents"] == 50


async def test_check_and_increment_usage_no_addon_raises(async_session):
    """Test that missing addon raises NoActiveVoiceAddonError."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    with pytest.raises(NoActiveVoiceAddonError):
        await check_and_increment_usage(async_session, tenant.id)


async def test_get_voice_usage_with_addon(async_session):
    """Test getting usage info when addon exists."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    addon = make_voice_addon(
        tenant_id=tenant.id,
        plan_name=VoiceAddonPlan.voice_pro,
        calls_limit=200,
        calls_used_this_period=75,
        period_start=now,
    )
    async_session.add(addon)
    await async_session.flush()

    usage = await get_voice_usage(async_session, tenant.id)
    assert usage["plan_name"] == "voice_pro"
    assert usage["is_active"] is True
    assert usage["calls_used"] == 75
    assert usage["calls_limit"] == 200
    assert usage["calls_remaining"] == 125
    assert usage["overage_calls"] == 0
    assert usage["overage_cost_cents"] == 0


async def test_get_voice_usage_no_addon(async_session):
    """Test getting usage info when no addon exists."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    usage = await get_voice_usage(async_session, tenant.id)
    assert usage["plan_name"] is None
    assert usage["is_active"] is False
    assert usage["calls_used"] == 0
    assert usage["calls_limit"] == 0


async def test_get_voice_usage_with_overage(async_session):
    """Test usage info correctly calculates overage."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = make_voice_addon(
        tenant_id=tenant.id,
        calls_limit=50,
        calls_used_this_period=63,
        overage_rate_cents=50,
    )
    async_session.add(addon)
    await async_session.flush()

    usage = await get_voice_usage(async_session, tenant.id)
    assert usage["calls_remaining"] == 0
    assert usage["overage_calls"] == 13
    assert usage["overage_cost_cents"] == 650  # 13 * 50 cents


async def test_reset_period_usage(async_session):
    """Test resetting usage for a new period."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = make_voice_addon(
        tenant_id=tenant.id, calls_used_this_period=42
    )
    async_session.add(addon)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    await reset_period_usage(async_session, tenant.id, now, now)

    result = await async_session.execute(
        select(VoiceAddon).where(VoiceAddon.id == addon.id)
    )
    updated = result.scalar_one()
    assert updated.calls_used_this_period == 0


# ---------- Voice Plans Config Tests ----------


def test_voice_plans_config():
    """Test that VOICE_PLANS configuration is complete."""
    assert "voice_starter" in VOICE_PLANS
    assert "voice_pro" in VOICE_PLANS
    assert "voice_scale" in VOICE_PLANS

    starter = VOICE_PLANS["voice_starter"]
    assert starter["price_cents"] == 2900
    assert starter["calls_included"] == 50
    assert starter["overage_rate_cents"] == 50

    pro = VOICE_PLANS["voice_pro"]
    assert pro["price_cents"] == 7900
    assert pro["calls_included"] == 200

    scale = VOICE_PLANS["voice_scale"]
    assert scale["price_cents"] == 19900
    assert scale["calls_included"] == 600


# ---------- Voice Addon Model Tests ----------


async def test_voice_addon_model_creation(async_session):
    """Test VoiceAddon model can be persisted."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    addon = VoiceAddon(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        plan_name=VoiceAddonPlan.voice_scale,
        calls_limit=600,
        calls_used_this_period=0,
        overage_rate_cents=50,
        is_active=True,
    )
    async_session.add(addon)
    await async_session.flush()

    result = await async_session.execute(
        select(VoiceAddon).where(VoiceAddon.id == addon.id)
    )
    stored = result.scalar_one()
    assert stored.plan_name == VoiceAddonPlan.voice_scale
    assert stored.calls_limit == 600
    assert stored.overage_rate_cents == 50


async def test_voice_addon_plan_enum():
    """Test VoiceAddonPlan enum has correct values."""
    assert VoiceAddonPlan.voice_starter.value == "voice_starter"
    assert VoiceAddonPlan.voice_pro.value == "voice_pro"
    assert VoiceAddonPlan.voice_scale.value == "voice_scale"


# ---------- Voice Billing Routes Tests ----------


async def test_list_voice_plans_endpoint():
    """Test that GET /api/billing/voice-plans endpoint is registered."""
    from dashboard.routes.voice_billing import router

    plan_routes = [
        r
        for r in router.routes
        if hasattr(r, "path")
        and r.path == "/api/billing/voice-plans"
        and "GET" in r.methods
    ]
    assert len(plan_routes) == 1


async def test_voice_addon_checkout_endpoint():
    """Test that POST /api/billing/voice-addon/checkout endpoint is registered."""
    from dashboard.routes.voice_billing import router

    checkout_routes = [
        r
        for r in router.routes
        if hasattr(r, "path")
        and r.path == "/api/billing/voice-addon/checkout"
        and "POST" in r.methods
    ]
    assert len(checkout_routes) == 1


async def test_voice_usage_endpoint():
    """Test that GET /api/billing/voice-usage endpoint is registered."""
    from dashboard.routes.voice_billing import router

    usage_routes = [
        r
        for r in router.routes
        if hasattr(r, "path")
        and r.path == "/api/billing/voice-usage"
        and "GET" in r.methods
    ]
    assert len(usage_routes) == 1


async def test_voice_addon_cancel_endpoint():
    """Test that POST /api/billing/voice-addon/cancel endpoint is registered."""
    from dashboard.routes.voice_billing import router

    cancel_routes = [
        r
        for r in router.routes
        if hasattr(r, "path")
        and r.path == "/api/billing/voice-addon/cancel"
        and "POST" in r.methods
    ]
    assert len(cancel_routes) == 1


# ---------- CallManager Integration Tests ----------


async def test_call_manager_rejects_without_addon(async_session, session_factory):
    """Test that CallManager rejects calls when no voice addon exists."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead_id = uuid.uuid4()
    mock_twilio = AsyncMock()
    mock_stt = AsyncMock()
    mock_tts = AsyncMock()
    mock_llm = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.tracking_base_url = "http://localhost:8000"
    mock_settings.voice_amd_enabled = False

    from channels.voice.call_manager import CallManager

    manager = CallManager(
        twilio_client=mock_twilio,
        stt=mock_stt,
        tts=mock_tts,
        llm_client=mock_llm,
        session_factory=session_factory,
        settings=mock_settings,
        redis_url="",
    )

    result = await manager.start_call(
        lead_id=lead_id,
        tenant_id=tenant.id,
    )

    assert result["status"] == "rejected"
    assert result["call_id"] is None
    assert "No active Voice AI add-on" in result["error"]


async def test_call_manager_allows_with_active_addon(async_session, session_factory):
    """Test that CallManager allows calls when voice addon is active."""
    from channels.voice.call_manager import CallManager
    from core.models import Lead, LeadStatus

    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = Lead(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email="test@example.com",
        first_name="John",
        last_name="Doe",
        company="Acme",
        title="CEO",
        status=LeadStatus.new,
        enrichment_data={"phone": "+15551234567"},
    )
    async_session.add(lead)

    addon = make_voice_addon(tenant_id=tenant.id, calls_limit=50, calls_used_this_period=0)
    async_session.add(addon)
    await async_session.flush()
    await async_session.commit()

    mock_twilio = AsyncMock()
    mock_twilio.initiate_call = AsyncMock(
        return_value={"call_sid": "CA123", "status": "initiated"}
    )
    mock_stt = AsyncMock()
    mock_tts = AsyncMock()
    mock_llm = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.tracking_base_url = "http://localhost:8000"
    mock_settings.voice_amd_enabled = False

    manager = CallManager(
        twilio_client=mock_twilio,
        stt=mock_stt,
        tts=mock_tts,
        llm_client=mock_llm,
        session_factory=session_factory,
        settings=mock_settings,
        redis_url="",
    )

    result = await manager.start_call(
        lead_id=lead.id,
        tenant_id=tenant.id,
    )

    assert result["status"] != "rejected"
    assert result["twilio_sid"] == "CA123"

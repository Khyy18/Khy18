"""Tests for the self-serve onboarding flow."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from core.models import Campaign, CampaignStatus, Sequence, Tenant
from dashboard.routes.onboarding import OnboardingService

# Import factory functions from conftest (available as module-level functions)
from tests.conftest import make_campaign, make_sequence, make_tenant, make_user


@pytest.fixture
def sample_onboarding_data():
    """Sample onboarding questionnaire data."""
    return {
        "company_description": "We build AI-powered sales tools",
        "ideal_customer_industry": "SaaS",
        "ideal_customer_company_size": "50-200",
        "ideal_customer_titles": "VP Sales, Head of Growth, CRO",
        "problem_solved": "Manual outbound is slow and expensive",
        "differentiator": "Fully autonomous AI that books meetings",
        "tone": "professional",
        "website_url": "https://example.com",
    }


@pytest.fixture
def mock_llm_for_onboarding():
    """Mock LLM client that returns a valid campaign plan JSON."""
    client = AsyncMock()
    plan = {
        "campaign_name": "SaaS Growth Outbound",
        "value_proposition": "Fully autonomous AI that books meetings for SaaS companies",
        "icp_filter": {
            "industry": "SaaS",
            "company_size": "50-200",
            "titles": "VP Sales, Head of Growth, CRO",
        },
        "sequence": [
            {
                "step_type": "initial",
                "subject": "Quick question about your outbound",
                "body": "Hi {{first_name}}, noticed your team is growing...",
            },
            {
                "step_type": "follow_up_1",
                "subject": "Following up",
                "body": "Hi {{first_name}}, just checking if you saw my previous note...",
            },
            {
                "step_type": "follow_up_2",
                "subject": "One last thought",
                "body": "Hi {{first_name}}, I wanted to share one more thing...",
            },
        ],
    }
    client.generate = AsyncMock(return_value=json.dumps(plan))
    return client


async def test_setup_stores_onboarding_data(async_session, sample_onboarding_data):
    """Test that setup endpoint stores onboarding data in tenant settings."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(session=async_session)
    result = await service.store_setup_data(
        tenant_id=tenant.id,
        data=sample_onboarding_data,
    )

    assert result == {"status": "ok", "step": "generate"}

    # Verify data is stored in tenant settings
    await async_session.refresh(tenant)
    assert tenant.settings["onboarding_data"] == sample_onboarding_data


async def test_generate_creates_campaign_and_sequence(
    async_session, sample_onboarding_data, mock_llm_for_onboarding
):
    """Test that generate endpoint creates a Campaign and Sequence in DB."""
    tenant = make_tenant(settings={"onboarding_data": sample_onboarding_data})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(
        session=async_session, llm_client=mock_llm_for_onboarding
    )
    preview = await service.generate_campaign(tenant_id=tenant.id)

    # Verify preview structure
    assert "campaign_name" in preview
    assert "value_proposition" in preview
    assert "icp_filter" in preview
    assert "sequence" in preview
    assert "campaign_id" in preview
    assert "sequence_id" in preview

    # Verify Campaign was created
    campaigns = (
        await async_session.execute(
            select(Campaign).where(Campaign.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(campaigns) == 1
    assert campaigns[0].status == CampaignStatus.draft
    assert campaigns[0].name == "SaaS Growth Outbound"

    # Verify Sequence was created
    sequences = (
        await async_session.execute(
            select(Sequence).where(Sequence.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(sequences) == 1
    assert len(sequences[0].steps) == 3

    # Verify LLM was called
    mock_llm_for_onboarding.generate.assert_called_once()


async def test_confirm_activates_campaign(async_session):
    """Test that confirm endpoint activates the draft campaign."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    # Create a draft campaign
    sequence = make_sequence(tenant_id=tenant.id)
    async_session.add(sequence)
    await async_session.flush()

    campaign = make_campaign(
        tenant_id=tenant.id,
        sequence_id=sequence.id,
        status=CampaignStatus.draft,
    )
    async_session.add(campaign)
    await async_session.flush()

    service = OnboardingService(session=async_session)
    result = await service.confirm_campaign(tenant_id=tenant.id)

    assert result["status"] == "activated"
    assert result["campaign_id"] == str(campaign.id)
    assert "3-5 days" in result["message"]

    # Verify campaign is now active
    await async_session.refresh(campaign)
    assert campaign.status == CampaignStatus.active


async def test_generate_without_setup_returns_error(async_session):
    """Test that calling generate without setup data returns an error."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    mock_llm = AsyncMock()
    service = OnboardingService(session=async_session, llm_client=mock_llm)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_campaign(tenant_id=tenant.id)

    assert exc_info.value.status_code == 400
    assert "No onboarding data found" in exc_info.value.detail


async def test_confirm_without_draft_returns_error(async_session):
    """Test that calling confirm with no draft campaign returns an error."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(session=async_session)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.confirm_campaign(tenant_id=tenant.id)

    assert exc_info.value.status_code == 404
    assert "No draft campaign found" in exc_info.value.detail


async def test_generate_handles_invalid_llm_response(
    async_session, sample_onboarding_data
):
    """Test that generate handles non-JSON LLM response gracefully with fallback."""
    tenant = make_tenant(settings={"onboarding_data": sample_onboarding_data})
    async_session.add(tenant)
    await async_session.flush()

    # LLM returns non-JSON
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Sorry, I cannot generate that.")

    service = OnboardingService(session=async_session, llm_client=mock_llm)
    preview = await service.generate_campaign(tenant_id=tenant.id)

    # Should still work with fallback plan
    assert "campaign_name" in preview
    assert "sequence" in preview

    # Verify Campaign and Sequence still created
    campaigns = (
        await async_session.execute(
            select(Campaign).where(Campaign.tenant_id == tenant.id)
        )
    ).scalars().all()
    assert len(campaigns) == 1


async def test_setup_stores_data_preserving_existing_settings(async_session, sample_onboarding_data):
    """Test that setup preserves existing tenant settings."""
    tenant = make_tenant(settings={"existing_key": "existing_value"})
    async_session.add(tenant)
    await async_session.flush()

    service = OnboardingService(session=async_session)
    await service.store_setup_data(tenant_id=tenant.id, data=sample_onboarding_data)

    await async_session.refresh(tenant)
    assert tenant.settings["existing_key"] == "existing_value"
    assert tenant.settings["onboarding_data"] == sample_onboarding_data


# ---------- Step-based Onboarding Flow Tests ----------

from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from core.models import OnboardingStep
from dashboard.routes.onboarding import router as onboarding_router


def _make_onboarding_app(session_factory, tenant_id):
    """Create a FastAPI app with onboarding router and mocked auth/session."""
    from fastapi import FastAPI
    from core.models import User, UserRole
    from dashboard.auth import get_current_user
    from dashboard.routes.onboarding import _get_session
    import uuid as _uuid

    app = FastAPI()
    app.include_router(onboarding_router)

    mock_user = MagicMock(spec=User)
    mock_user.id = _uuid.uuid4()
    mock_user.tenant_id = tenant_id
    mock_user.email = "test@example.com"
    mock_user.role = UserRole.admin

    async def _override_user():
        return mock_user

    async def _override_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_get_session] = _override_session
    return app


async def test_onboarding_status_returns_current_step(async_session, session_factory):
    """Test GET /api/onboarding/status returns the current step."""
    tenant = make_tenant(settings={}, onboarding_step=OnboardingStep.tenant_created)
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()

    app = _make_onboarding_app(session_factory, tenant.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/onboarding/status")

    assert response.status_code == 200
    data = response.json()
    assert data["current_step"] == "tenant_created"
    assert data["steps_completed"] == []
    assert data["tenant_id"] == str(tenant.id)


async def test_step1_advances_to_smtp_connected(async_session, session_factory):
    """Test POST /api/onboarding/step1 updates tenant and advances step."""
    tenant = make_tenant(settings={}, onboarding_step=OnboardingStep.tenant_created)
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()
    tenant_id = tenant.id

    app = _make_onboarding_app(session_factory, tenant_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/onboarding/step1",
            json={"company_name": "Acme Corp", "domain": "acme.com"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["next_step"] == "smtp_connected"

    # Verify tenant was updated (re-query from DB)
    async_session.expire_all()
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    updated_tenant = result.scalar_one()
    assert updated_tenant.name == "Acme Corp"
    assert updated_tenant.domain == "acme.com"
    assert updated_tenant.onboarding_step == OnboardingStep.smtp_connected


async def test_step2_tests_smtp_and_advances(async_session, session_factory):
    """Test POST /api/onboarding/step2 with mocked successful SMTP connection."""
    tenant = make_tenant(settings={}, onboarding_step=OnboardingStep.smtp_connected)
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()
    tenant_id = tenant.id

    app = _make_onboarding_app(session_factory, tenant_id)
    transport = ASGITransport(app=app)

    with patch("dashboard.routes.onboarding.aiosmtplib") as mock_aiosmtplib:
        mock_smtp_instance = AsyncMock()
        mock_smtp_instance.connect = AsyncMock()
        mock_smtp_instance.quit = AsyncMock()
        mock_aiosmtplib.SMTP.return_value = mock_smtp_instance

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/onboarding/step2",
                json={
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "smtp_user": "user@example.com",
                    "smtp_password": "secret",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["next_step"] == "icp_uploaded"

    # Verify SMTP config stored in settings (re-query)
    async_session.expire_all()
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    updated_tenant = result.scalar_one()
    assert updated_tenant.settings["smtp"]["host"] == "smtp.example.com"
    assert updated_tenant.settings["smtp"]["port"] == 587
    assert updated_tenant.onboarding_step == OnboardingStep.icp_uploaded


async def test_step2_fails_on_bad_smtp(async_session, session_factory):
    """Test POST /api/onboarding/step2 returns 422 on SMTP failure."""
    tenant = make_tenant(settings={}, onboarding_step=OnboardingStep.smtp_connected)
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()
    tenant_id = tenant.id

    app = _make_onboarding_app(session_factory, tenant_id)
    transport = ASGITransport(app=app)

    with patch("dashboard.routes.onboarding.aiosmtplib") as mock_aiosmtplib:
        mock_smtp_instance = AsyncMock()
        mock_smtp_instance.connect = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        mock_aiosmtplib.SMTP.return_value = mock_smtp_instance

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/onboarding/step2",
                json={
                    "smtp_host": "bad-host.example.com",
                    "smtp_port": 587,
                    "smtp_user": "user@example.com",
                    "smtp_password": "secret",
                },
            )

    assert response.status_code == 422
    data = response.json()
    assert "SMTP connection failed" in data["detail"]

    # Verify step did NOT advance (re-query)
    async_session.expire_all()
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    updated_tenant = result.scalar_one()
    assert updated_tenant.onboarding_step == OnboardingStep.smtp_connected


async def test_step3_stores_icp_and_advances(async_session, session_factory):
    """Test POST /api/onboarding/step3 stores ICP data and advances step."""
    tenant = make_tenant(settings={}, onboarding_step=OnboardingStep.icp_uploaded)
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()
    tenant_id = tenant.id

    app = _make_onboarding_app(session_factory, tenant_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/onboarding/step3",
            json={
                "industry": "SaaS",
                "company_size": "50-200",
                "titles": ["VP Sales", "CRO"],
                "geo": "US",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["next_step"] == "campaign_activated"

    # Verify ICP data stored (re-query)
    async_session.expire_all()
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    updated_tenant = result.scalar_one()
    assert updated_tenant.settings["icp"]["industry"] == "SaaS"
    assert updated_tenant.settings["icp"]["titles"] == ["VP Sales", "CRO"]
    assert updated_tenant.settings["icp"]["geo"] == "US"
    assert updated_tenant.onboarding_step == OnboardingStep.campaign_activated


async def test_step4_creates_campaign_and_completes(async_session, session_factory):
    """Test POST /api/onboarding/step4 creates campaign and completes onboarding."""
    tenant = make_tenant(
        settings={"icp": {"industry": "SaaS", "company_size": "50-200", "titles": ["VP Sales"], "geo": "US"}},
        onboarding_step=OnboardingStep.campaign_activated,
    )
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()
    tenant_id = tenant.id

    app = _make_onboarding_app(session_factory, tenant_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/onboarding/step4",
            json={"campaign_name": "My First Campaign"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "campaign_id" in data
    assert "Onboarding complete" in data["message"]

    # Verify tenant is completed (re-query)
    async_session.expire_all()
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    updated_tenant = result.scalar_one()
    assert updated_tenant.onboarding_step == OnboardingStep.completed

    # Verify campaign was created and is active
    camp_result = await async_session.execute(
        select(Campaign).where(Campaign.tenant_id == tenant_id)
    )
    campaigns = camp_result.scalars().all()
    assert len(campaigns) == 1
    assert campaigns[0].status == CampaignStatus.active
    assert campaigns[0].name == "My First Campaign"


async def test_step_order_enforced(async_session, session_factory):
    """Test that steps cannot be skipped - must complete in order."""
    tenant = make_tenant(settings={}, onboarding_step=OnboardingStep.tenant_created)
    async_session.add(tenant)
    await async_session.flush()
    await async_session.commit()

    app = _make_onboarding_app(session_factory, tenant.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try step2 without completing step1
        response = await client.post(
            "/api/onboarding/step2",
            json={
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_user": "user@example.com",
                "smtp_password": "secret",
            },
        )
        assert response.status_code == 400
        assert "Complete previous steps" in response.json()["detail"]

        # Try step3 without completing step1/step2
        response = await client.post(
            "/api/onboarding/step3",
            json={
                "industry": "SaaS",
                "company_size": "50-200",
                "titles": ["VP Sales"],
                "geo": "US",
            },
        )
        assert response.status_code == 400

        # Try step4 without completing previous steps
        response = await client.post(
            "/api/onboarding/step4",
            json={"campaign_name": "Test"},
        )
        assert response.status_code == 400

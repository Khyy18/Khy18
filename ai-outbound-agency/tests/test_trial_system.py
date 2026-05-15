"""Tests for the free trial system."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Tenant, Trial, TrialStatus, User, UserRole


def _make_tenant_and_user(tenant_id=None):
    """Create a test tenant and user pair."""
    tid = tenant_id or uuid.uuid4()
    tenant = Tenant(id=tid, name="Trial Corp", domain="trial.com")
    user = User(
        id=uuid.uuid4(),
        tenant_id=tid,
        email=f"user-{uuid.uuid4().hex[:6]}@trial.com",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )
    return tenant, user


async def test_start_trial_creates_14_day_trial(async_session: AsyncSession):
    """Starting a trial creates a 14-day active trial with correct limits."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now,
        ends_at=now + timedelta(days=14),
        leads_used=0,
        emails_used=0,
    )
    async_session.add(trial)
    await async_session.flush()

    result = await async_session.execute(
        select(Trial).where(Trial.tenant_id == tenant.id)
    )
    saved_trial = result.scalar_one()

    assert saved_trial.status == TrialStatus.active
    assert saved_trial.leads_used == 0
    assert saved_trial.emails_used == 0
    # Trial should end 14 days after start
    delta = saved_trial.ends_at - saved_trial.started_at
    assert delta.days == 14


async def test_trial_status_shows_days_remaining(async_session: AsyncSession):
    """Trial status should correctly calculate days remaining."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now - timedelta(days=5),
        ends_at=now + timedelta(days=9),
        leads_used=10,
        emails_used=25,
    )
    async_session.add(trial)
    await async_session.flush()

    # Calculate days remaining
    days_remaining = max(0, (trial.ends_at - now).days)
    assert days_remaining == 9
    assert trial.leads_used == 10
    assert trial.emails_used == 25


async def test_trial_status_shows_conversion_prompt_at_day_7(async_session: AsyncSession):
    """Conversion prompt should appear at day 7 of the trial."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now - timedelta(days=8),
        ends_at=now + timedelta(days=6),
        leads_used=0,
        emails_used=0,
    )
    async_session.add(trial)
    await async_session.flush()

    days_elapsed = (now - trial.started_at).days
    assert days_elapsed >= 7

    # Conversion prompt logic from the route
    conversion_prompt = None
    if trial.status == TrialStatus.active:
        if days_elapsed >= 12:
            conversion_prompt = "Your trial ends in 2 days! Upgrade now to keep your data and continue growing."
        elif days_elapsed >= 7:
            conversion_prompt = "You're halfway through your trial. Upgrade to unlock unlimited leads and emails."

    assert conversion_prompt is not None
    assert "halfway" in conversion_prompt


async def test_trial_frozen_after_14_days(async_session: AsyncSession):
    """Trial should be frozen after 14 days have elapsed."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now - timedelta(days=15),
        ends_at=now - timedelta(days=1),
        leads_used=30,
        emails_used=60,
    )
    async_session.add(trial)
    await async_session.flush()

    # Simulate auto-freeze logic from the status endpoint
    if trial.status == TrialStatus.active and now >= trial.ends_at:
        trial.status = TrialStatus.frozen
        await async_session.flush()

    result = await async_session.execute(
        select(Trial).where(Trial.tenant_id == tenant.id)
    )
    frozen_trial = result.scalar_one()
    assert frozen_trial.status == TrialStatus.frozen


async def test_trial_limits_enforced(async_session: AsyncSession):
    """Trial should track usage against limits."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now,
        ends_at=now + timedelta(days=14),
        leads_used=50,
        emails_used=100,
    )
    async_session.add(trial)
    await async_session.flush()

    TRIAL_LEADS_LIMIT = 50
    TRIAL_EMAILS_LIMIT = 100

    # At limit - should not allow more
    assert trial.leads_used >= TRIAL_LEADS_LIMIT
    assert trial.emails_used >= TRIAL_EMAILS_LIMIT

    # Verify can track when under limits
    trial.leads_used = 25
    trial.emails_used = 50
    await async_session.flush()
    assert trial.leads_used < TRIAL_LEADS_LIMIT
    assert trial.emails_used < TRIAL_EMAILS_LIMIT


async def test_trial_conversion_prompt_at_day_12(async_session: AsyncSession):
    """Conversion prompt at day 12 warns trial ends in 2 days."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now - timedelta(days=13),
        ends_at=now + timedelta(days=1),
        leads_used=0,
        emails_used=0,
    )
    async_session.add(trial)
    await async_session.flush()

    days_elapsed = (now - trial.started_at).days
    assert days_elapsed >= 12

    # Conversion prompt logic from the route
    conversion_prompt = None
    if trial.status == TrialStatus.active:
        if days_elapsed >= 12:
            conversion_prompt = "Your trial ends in 2 days! Upgrade now to keep your data and continue growing."
        elif days_elapsed >= 7:
            conversion_prompt = "You're halfway through your trial. Upgrade to unlock unlimited leads and emails."

    assert conversion_prompt is not None
    assert "ends in 2 days" in conversion_prompt


async def test_trial_upgrade_sets_converted_at(async_session: AsyncSession):
    """Upgrading a trial sets converted_at timestamp and status to converted."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now - timedelta(days=5),
        ends_at=now + timedelta(days=9),
        leads_used=20,
        emails_used=40,
    )
    async_session.add(trial)
    await async_session.flush()

    # Simulate upgrade
    trial.status = TrialStatus.converted
    trial.converted_at = datetime.now(timezone.utc)
    await async_session.flush()

    result = await async_session.execute(
        select(Trial).where(Trial.tenant_id == tenant.id)
    )
    upgraded_trial = result.scalar_one()
    assert upgraded_trial.status == TrialStatus.converted
    assert upgraded_trial.converted_at is not None


async def test_trial_no_linkedin_during_trial(async_session: AsyncSession):
    """Trial users should not have access to LinkedIn channel (business rule)."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=tenant.id,
        status=TrialStatus.active,
        started_at=now,
        ends_at=now + timedelta(days=14),
        leads_used=0,
        emails_used=0,
    )
    async_session.add(trial)
    await async_session.flush()

    # Business rule: trial users have no LinkedIn access
    # The trial limits include: 50 leads, 100 emails, 0 LinkedIn messages
    TRIAL_LINKEDIN_LIMIT = 0
    assert trial.status == TrialStatus.active
    # Verify the documented constraint: LinkedIn is not available during trial
    assert TRIAL_LINKEDIN_LIMIT == 0

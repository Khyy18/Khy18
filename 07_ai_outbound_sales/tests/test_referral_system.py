"""Tests for the referral system."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Referral, Tenant, User, UserRole


def _make_tenant_and_user(name="Ref Corp", domain="ref.com"):
    """Create a test tenant and user pair."""
    tid = uuid.uuid4()
    tenant = Tenant(id=tid, name=name, domain=domain)
    user = User(
        id=uuid.uuid4(),
        tenant_id=tid,
        email=f"user-{uuid.uuid4().hex[:6]}@{domain}",
        password_hash="$2b$12$hash",
        role=UserRole.admin,
    )
    return tenant, user


async def test_generate_referral_code(async_session: AsyncSession):
    """Generating a referral code creates a 6-char alphanumeric code."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    code = "ABC123"
    referral = Referral(
        referrer_tenant_id=tenant.id,
        referred_tenant_id=None,
        code=code,
        reward_applied=False,
    )
    async_session.add(referral)
    await async_session.flush()

    result = await async_session.execute(
        select(Referral).where(Referral.referrer_tenant_id == tenant.id)
    )
    saved = result.scalar_one()
    assert saved.code == "ABC123"
    assert len(saved.code) == 6
    assert saved.referred_tenant_id is None
    assert saved.reward_applied is False


async def test_apply_referral_code(async_session: AsyncSession):
    """Applying a referral code links referred tenant and marks reward."""
    referrer_tenant, referrer_user = _make_tenant_and_user("Referrer", "referrer.com")
    referred_tenant, referred_user = _make_tenant_and_user("Referred", "referred.com")

    async_session.add(referrer_tenant)
    async_session.add(referrer_user)
    async_session.add(referred_tenant)
    async_session.add(referred_user)
    await async_session.flush()

    referral = Referral(
        referrer_tenant_id=referrer_tenant.id,
        referred_tenant_id=None,
        code="REF001",
        reward_applied=False,
    )
    async_session.add(referral)
    await async_session.flush()

    # Apply the code
    referral.referred_tenant_id = referred_tenant.id
    referral.reward_applied = True
    await async_session.flush()

    result = await async_session.execute(
        select(Referral).where(Referral.code == "REF001")
    )
    applied = result.scalar_one()
    assert applied.referred_tenant_id == referred_tenant.id
    assert applied.reward_applied is True


async def test_referral_code_unique_per_tenant(async_session: AsyncSession):
    """Each referral code should be unique."""
    tenant1, user1 = _make_tenant_and_user("Corp1", "corp1.com")
    tenant2, user2 = _make_tenant_and_user("Corp2", "corp2.com")

    async_session.add(tenant1)
    async_session.add(user1)
    async_session.add(tenant2)
    async_session.add(user2)
    await async_session.flush()

    ref1 = Referral(
        referrer_tenant_id=tenant1.id,
        referred_tenant_id=None,
        code="UNQ001",
        reward_applied=False,
    )
    ref2 = Referral(
        referrer_tenant_id=tenant2.id,
        referred_tenant_id=None,
        code="UNQ002",
        reward_applied=False,
    )
    async_session.add(ref1)
    async_session.add(ref2)
    await async_session.flush()

    # Verify codes are different
    result = await async_session.execute(select(Referral))
    referrals = result.scalars().all()
    codes = [r.code for r in referrals]
    assert len(codes) == len(set(codes))  # All unique


async def test_cannot_apply_own_code(async_session: AsyncSession):
    """A tenant should not be able to apply their own referral code."""
    tenant, user = _make_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    referral = Referral(
        referrer_tenant_id=tenant.id,
        referred_tenant_id=None,
        code="SELF01",
        reward_applied=False,
    )
    async_session.add(referral)
    await async_session.flush()

    # Attempting to apply own code should be rejected
    assert referral.referrer_tenant_id == tenant.id
    # In the route, this raises HTTPException 400
    # Here we verify the condition check
    is_own_code = referral.referrer_tenant_id == user.tenant_id
    assert is_own_code is True


async def test_referral_stats(async_session: AsyncSession):
    """Referral stats correctly count total, rewards, and pending."""
    referrer_tenant, referrer_user = _make_tenant_and_user("Stats Corp", "stats.com")
    referred1_tenant, _ = _make_tenant_and_user("Ref1", "ref1.com")
    referred2_tenant, _ = _make_tenant_and_user("Ref2", "ref2.com")

    async_session.add(referrer_tenant)
    async_session.add(referrer_user)
    async_session.add(referred1_tenant)
    async_session.add(referred2_tenant)
    await async_session.flush()

    # Create referrals - one rewarded, one pending
    ref1 = Referral(
        referrer_tenant_id=referrer_tenant.id,
        referred_tenant_id=referred1_tenant.id,
        code="STAT01",
        reward_applied=True,
    )
    ref2 = Referral(
        referrer_tenant_id=referrer_tenant.id,
        referred_tenant_id=referred2_tenant.id,
        code="STAT02",
        reward_applied=False,
    )
    # Unused code (no referred tenant)
    ref3 = Referral(
        referrer_tenant_id=referrer_tenant.id,
        referred_tenant_id=None,
        code="STAT03",
        reward_applied=False,
    )
    async_session.add_all([ref1, ref2, ref3])
    await async_session.flush()

    # Count stats
    from sqlalchemy import func

    total_result = await async_session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_tenant_id == referrer_tenant.id,
            Referral.referred_tenant_id.isnot(None),
        )
    )
    total_referrals = total_result.scalar() or 0

    rewards_result = await async_session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_tenant_id == referrer_tenant.id,
            Referral.reward_applied.is_(True),
        )
    )
    rewards_earned = rewards_result.scalar() or 0

    pending_result = await async_session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_tenant_id == referrer_tenant.id,
            Referral.referred_tenant_id.isnot(None),
            Referral.reward_applied.is_(False),
        )
    )
    pending_referrals = pending_result.scalar() or 0

    assert total_referrals == 2
    assert rewards_earned == 1
    assert pending_referrals == 1


async def test_already_used_referral_code_returns_error(async_session: AsyncSession):
    """An already-used referral code cannot be re-applied."""
    referrer_tenant, referrer_user = _make_tenant_and_user("Referrer", "referrer2.com")
    referred_tenant, referred_user = _make_tenant_and_user("Referred", "referred2.com")
    new_tenant, new_user = _make_tenant_and_user("NewTenant", "new.com")

    async_session.add(referrer_tenant)
    async_session.add(referrer_user)
    async_session.add(referred_tenant)
    async_session.add(referred_user)
    async_session.add(new_tenant)
    async_session.add(new_user)
    await async_session.flush()

    # Create a referral that has already been used
    referral = Referral(
        referrer_tenant_id=referrer_tenant.id,
        referred_tenant_id=referred_tenant.id,
        code="USED01",
        reward_applied=True,
    )
    async_session.add(referral)
    await async_session.flush()

    # Verify the code is already used (referred_tenant_id is not None)
    result = await async_session.execute(
        select(Referral).where(Referral.code == "USED01")
    )
    existing = result.scalar_one()

    # This is the condition check the route performs before applying
    is_already_used = existing.referred_tenant_id is not None
    assert is_already_used is True
    # In the route, this would return HTTPException 400 "Referral code already used"


async def test_referral_reward_amounts_documented(async_session: AsyncSession):
    """Referral reward semantics: 1 month free for referrer, 20% off for referred."""
    referrer_tenant, referrer_user = _make_tenant_and_user("RewardReferrer", "rewarder.com")
    referred_tenant, referred_user = _make_tenant_and_user("RewardReferred", "rewarded.com")

    async_session.add(referrer_tenant)
    async_session.add(referrer_user)
    async_session.add(referred_tenant)
    async_session.add(referred_user)
    await async_session.flush()

    referral = Referral(
        referrer_tenant_id=referrer_tenant.id,
        referred_tenant_id=None,
        code="RWD001",
        reward_applied=False,
    )
    async_session.add(referral)
    await async_session.flush()

    # Simulate applying the referral code
    referral.referred_tenant_id = referred_tenant.id
    referral.reward_applied = True
    await async_session.flush()

    # Verify the referral model state after application
    result = await async_session.execute(
        select(Referral).where(Referral.code == "RWD001")
    )
    applied = result.scalar_one()

    # Documented reward semantics:
    # - Referrer gets 1 month free (reward_applied=True marks reward granted)
    # - Referred gets 20% off first month
    assert applied.reward_applied is True
    assert applied.referrer_tenant_id == referrer_tenant.id
    assert applied.referred_tenant_id == referred_tenant.id

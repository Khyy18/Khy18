"""Tests for the FeedbackCollector agent and feedback summary."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import LeadFeedback
from agents.feedback_collector import FeedbackCollector
from tests.conftest import make_lead, make_tenant, make_user


@pytest.fixture
async def feedback_tenant(async_session: AsyncSession):
    """Create a tenant with notification channels for feedback tests."""
    tenant = make_tenant(
        settings={
            "notification_channels": [
                {"type": "telegram", "bot_token": "test-token", "chat_id": "123"}
            ],
            "notification_preferences": {"real_time_alerts": True},
        }
    )
    async_session.add(tenant)
    await async_session.flush()
    return tenant


@pytest.fixture
async def feedback_lead(async_session: AsyncSession, feedback_tenant):
    """Create a lead for feedback tests."""
    lead = make_lead(tenant_id=feedback_tenant.id)
    async_session.add(lead)
    await async_session.flush()
    return lead


@pytest.fixture
async def feedback_user(async_session: AsyncSession, feedback_tenant):
    """Create a user for feedback tests."""
    user = make_user(tenant_id=feedback_tenant.id)
    async_session.add(user)
    await async_session.flush()
    return user


async def test_collect_feedback_stores_record(session_factory, async_session, feedback_tenant, feedback_lead):
    """Test that collect_feedback stores a LeadFeedback record in the database."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    collector = FeedbackCollector(session_factory=session_factory, settings=settings)

    feedback = await collector.collect_feedback(
        lead_id=feedback_lead.id,
        tenant_id=feedback_tenant.id,
        rating=4,
        comment="Great lead quality",
        feedback_type="lead_quality",
        event_trigger="meeting_booked",
    )

    assert feedback.id is not None
    assert feedback.rating == 4
    assert feedback.comment == "Great lead quality"
    assert feedback.feedback_type == "lead_quality"
    assert feedback.event_trigger == "meeting_booked"
    assert feedback.tenant_id == feedback_tenant.id
    assert feedback.lead_id == feedback_lead.id

    # Verify it was persisted
    result = await async_session.execute(
        select(func.count(LeadFeedback.id)).where(
            LeadFeedback.tenant_id == feedback_tenant.id,
        )
    )
    count = result.scalar()
    assert count == 1


async def test_feedback_summary_aggregation(async_session: AsyncSession, feedback_tenant, feedback_lead, feedback_user):
    """Test feedback summary aggregation returns correct stats."""
    # Create multiple feedbacks
    feedbacks_data = [
        {"rating": 5, "comment": "Excellent", "feedback_type": "lead_quality", "event_trigger": "meeting_booked"},
        {"rating": 4, "comment": "Good lead", "feedback_type": "lead_quality", "event_trigger": "manual"},
        {"rating": 3, "comment": None, "feedback_type": "message_quality", "event_trigger": "manual"},
        {"rating": 2, "comment": "Poor fit", "feedback_type": "general", "event_trigger": "negative_reply"},
        {"rating": 1, "comment": "Not relevant", "feedback_type": "lead_quality", "event_trigger": "manual"},
    ]

    for fd in feedbacks_data:
        fb = LeadFeedback(
            lead_id=feedback_lead.id,
            tenant_id=feedback_tenant.id,
            rating=fd["rating"],
            comment=fd["comment"],
            feedback_type=fd["feedback_type"],
            event_trigger=fd["event_trigger"],
        )
        async_session.add(fb)
    await async_session.commit()

    # Check average rating
    avg_result = await async_session.execute(
        select(func.avg(LeadFeedback.rating)).where(
            LeadFeedback.tenant_id == feedback_tenant.id,
        )
    )
    average_rating = avg_result.scalar() or 0.0
    assert round(float(average_rating), 2) == 3.0

    # Check total count
    count_result = await async_session.execute(
        select(func.count(LeadFeedback.id)).where(
            LeadFeedback.tenant_id == feedback_tenant.id,
        )
    )
    total_count = count_result.scalar() or 0
    assert total_count == 5

    # Check rating distribution
    dist_result = await async_session.execute(
        select(LeadFeedback.rating, func.count(LeadFeedback.id)).where(
            LeadFeedback.tenant_id == feedback_tenant.id,
        ).group_by(LeadFeedback.rating)
    )
    rating_distribution = {str(row[0]): row[1] for row in dist_result.all()}
    assert rating_distribution["5"] == 1
    assert rating_distribution["4"] == 1
    assert rating_distribution["3"] == 1
    assert rating_distribution["2"] == 1
    assert rating_distribution["1"] == 1

    # Check recent comments (excludes None)
    comments_result = await async_session.execute(
        select(LeadFeedback.comment)
        .where(
            LeadFeedback.tenant_id == feedback_tenant.id,
            LeadFeedback.comment.isnot(None),
        )
        .order_by(LeadFeedback.created_at.desc())
        .limit(10)
    )
    comments = [row[0] for row in comments_result.all()]
    assert len(comments) == 4  # One feedback had None comment


async def test_process_feedback_batch_recommendations(session_factory, async_session, feedback_tenant, feedback_lead):
    """Test that process_feedback_batch returns recommendations based on ratings."""
    from unittest.mock import MagicMock

    settings = MagicMock()

    # Create mostly low-rated feedback
    for i in range(5):
        fb = LeadFeedback(
            lead_id=feedback_lead.id,
            tenant_id=feedback_tenant.id,
            rating=2,
            comment="Not great",
            feedback_type="lead_quality",
            event_trigger="manual",
        )
        async_session.add(fb)
    await async_session.commit()

    collector = FeedbackCollector(session_factory=session_factory, settings=settings)
    result = await collector.process_feedback_batch(feedback_tenant.id)

    assert result["total_feedbacks"] == 5
    assert result["average_rating"] == 2.0
    assert len(result["recommendations"]) > 0
    # Should recommend ICP refinement due to low ratings
    assert any("ICP" in r or "targeting" in r.lower() for r in result["recommendations"])


async def test_process_feedback_batch_high_ratings(session_factory, async_session, feedback_tenant, feedback_lead):
    """Test that high ratings produce lookalike recommendations."""
    from unittest.mock import MagicMock

    settings = MagicMock()

    # Create mostly high-rated feedback
    for i in range(5):
        fb = LeadFeedback(
            lead_id=feedback_lead.id,
            tenant_id=feedback_tenant.id,
            rating=5,
            comment="Great lead",
            feedback_type="lead_quality",
            event_trigger="meeting_booked",
        )
        async_session.add(fb)
    await async_session.commit()

    collector = FeedbackCollector(session_factory=session_factory, settings=settings)
    result = await collector.process_feedback_batch(feedback_tenant.id)

    assert result["total_feedbacks"] == 5
    assert result["average_rating"] == 5.0
    assert any("lookalike" in r.lower() for r in result["recommendations"])


async def test_process_feedback_batch_empty(session_factory, feedback_tenant):
    """Test process_feedback_batch with no feedback returns empty recommendations."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    collector = FeedbackCollector(session_factory=session_factory, settings=settings)
    result = await collector.process_feedback_batch(feedback_tenant.id)

    assert result["total_feedbacks"] == 0
    assert result["average_rating"] == 0.0
    assert result["recommendations"] == []

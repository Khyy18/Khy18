"""Tests for TimingPredictor."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from agents.timing_predictor import TimeSlot, TimingPredictor
from core.models import Call, CallOutcome, CallStatus, Lead, LeadStatus
from tests.conftest import make_call, make_lead, make_tenant


@pytest.fixture
def predictor(session_factory, mock_settings):
    """Create a TimingPredictor instance."""
    return TimingPredictor(
        session_factory=session_factory,
        settings=mock_settings,
    )


@pytest.fixture
async def seed_timing_data(async_session):
    """Seed database with call data for training."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    # Create leads with enrichment data
    leads = []
    for i in range(5):
        lead = make_lead(
            tenant_id=tenant.id,
            title="VP of Sales",
            enrichment_data={"timezone": "US/Eastern", "industry": "technology"},
        )
        async_session.add(lead)
        leads.append(lead)
    await async_session.flush()

    # Create calls at different times with different outcomes
    for i in range(15):
        lead = leads[i % len(leads)]
        hour = 9 + (i % 9)  # Hours 9-17
        day_offset = i % 5
        started = datetime(2024, 1, 1 + day_offset, hour, 0, tzinfo=timezone.utc)
        outcome = CallOutcome.qualified if i % 3 == 0 else CallOutcome.not_interested
        call = make_call(
            tenant_id=tenant.id,
            lead_id=lead.id,
            status=CallStatus.completed,
            outcome=outcome,
            started_at=started,
        )
        async_session.add(call)

    await async_session.commit()
    return {"tenant": tenant, "leads": leads}


async def test_train_with_data(predictor, seed_timing_data):
    """Test model training with sample data."""
    tenant = seed_timing_data["tenant"]
    await predictor.train(tenant_id=tenant.id)

    assert predictor._is_trained is True
    assert predictor._model is not None


async def test_train_insufficient_data(predictor, async_session):
    """Test handling of insufficient training data."""
    # No data seeded - should not train
    await predictor.train(tenant_id=uuid.uuid4())

    assert predictor._is_trained is False
    assert predictor._model is None


async def test_predict_best_times_untrained(predictor, seed_timing_data):
    """Test prediction output format when model is not trained."""
    lead = seed_timing_data["leads"][0]

    # Without training, should return uniform distribution
    slots = await predictor.predict_best_times(lead.id)

    assert len(slots) > 0
    assert all(isinstance(s, TimeSlot) for s in slots)
    # Uniform distribution over business hours Mon-Fri
    assert len(slots) == 45  # 5 days * 9 hours


async def test_predict_best_times_trained(predictor, seed_timing_data):
    """Test prediction after training."""
    tenant = seed_timing_data["tenant"]
    lead = seed_timing_data["leads"][0]

    await predictor.train(tenant_id=tenant.id)
    slots = await predictor.predict_best_times(lead.id)

    assert len(slots) > 0
    assert all(isinstance(s, TimeSlot) for s in slots)
    # Should be sorted by probability descending
    for i in range(len(slots) - 1):
        assert slots[i].probability >= slots[i + 1].probability


async def test_predict_answer_probability_untrained(predictor):
    """Test raw prediction without training returns 0.5."""
    prob = predictor.predict_answer_probability({
        "timezone": "US/Eastern",
        "industry": "technology",
        "seniority": "vp",
        "day_of_week": 1,
        "hour": 10,
    })

    assert prob == 0.5


async def test_predict_answer_probability_trained(predictor, seed_timing_data):
    """Test raw prediction after training."""
    tenant = seed_timing_data["tenant"]
    await predictor.train(tenant_id=tenant.id)

    prob = predictor.predict_answer_probability({
        "timezone": "US/Eastern",
        "industry": "technology",
        "seniority": "vp",
        "day_of_week": 1,
        "hour": 10,
    })

    assert 0.0 <= prob <= 1.0


async def test_feature_encoding(predictor):
    """Test feature encoding consistency."""
    # Same value should get same encoding
    enc1 = predictor._encode_feature("timezone", "US/Eastern")
    enc2 = predictor._encode_feature("timezone", "US/Eastern")
    assert enc1 == enc2

    # Different values should get different encodings
    enc3 = predictor._encode_feature("timezone", "US/Pacific")
    assert enc1 != enc3


async def test_time_slot_model():
    """Test TimeSlot Pydantic model."""
    slot = TimeSlot(day_of_week=1, hour=10, probability=0.85, timezone="US/Eastern")
    assert slot.day_of_week == 1
    assert slot.hour == 10
    assert slot.probability == 0.85
    assert slot.timezone == "US/Eastern"

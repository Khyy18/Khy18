"""Tests for reviews module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import reviews
import database


@pytest.mark.asyncio
class TestReviews:
    """Tests for review system module."""

    async def test_auto_moderate_clean_text(self, initialized_db):
        """auto_moderate returns True for clean text."""
        assert reviews.auto_moderate("Great service, very fast!") is True
        assert reviews.auto_moderate("Отличная работа, спасибо!") is True

    async def test_auto_moderate_profanity(self, initialized_db):
        """auto_moderate returns False for profane text."""
        assert reviews.auto_moderate("This is shit service") is False
        assert reviews.auto_moderate("Полный пиздец") is False

    async def test_submit_review_clean(self, initialized_db):
        """submit_review saves clean review with pending status."""
        await database.get_or_create_client(telegram_id=100, username="reviewer")
        order_id = await database.create_order(
            client_id=100, service_type="rewrite", input_text="test", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=100, order_id=order_id, text="Great work!", rating=5
        )
        assert review_id is not None

        pending = await reviews.get_pending_reviews()
        assert len(pending) >= 1
        assert pending[0]["text"] == "Great work!"
        assert pending[0]["status"] == "pending"

    async def test_submit_review_profane(self, initialized_db):
        """submit_review rejects profane text."""
        await database.get_or_create_client(telegram_id=101, username="baduser")
        order_id = await database.create_order(
            client_id=101, service_type="rewrite", input_text="test", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=101, order_id=order_id, text="What a shit!", rating=1
        )
        assert review_id is None

    async def test_approve_and_get_approved(self, initialized_db):
        """approve_review changes status and appears in get_approved_reviews."""
        await database.get_or_create_client(telegram_id=102, username="gooduser")
        order_id = await database.create_order(
            client_id=102, service_type="rewrite", input_text="test", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=102, order_id=order_id, text="Excellent!", rating=5
        )
        assert review_id is not None

        await reviews.approve_review(review_id)
        approved = await reviews.get_approved_reviews(limit=10)
        assert len(approved) >= 1
        assert approved[0]["status"] == "approved"

    async def test_get_review_count(self, initialized_db):
        """get_review_count returns correct count of approved reviews."""
        count_before = await reviews.get_review_count()

        await database.get_or_create_client(telegram_id=103, username="counter")
        order_id = await database.create_order(
            client_id=103, service_type="rewrite", input_text="test", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=103, order_id=order_id, text="Nice!", rating=4
        )
        await reviews.approve_review(review_id)

        count_after = await reviews.get_review_count()
        assert count_after == count_before + 1

    async def test_reject_review(self, initialized_db):
        """reject_review changes status to rejected."""
        await database.get_or_create_client(telegram_id=104, username="rejected")
        order_id = await database.create_order(
            client_id=104, service_type="rewrite", input_text="test", price=100.0
        )
        review_id = await reviews.submit_review(
            client_id=104, order_id=order_id, text="Meh...", rating=3
        )
        assert review_id is not None

        await reviews.reject_review(review_id)
        pending = await reviews.get_pending_reviews()
        # Should not be in pending anymore
        assert all(r["id"] != review_id for r in pending)

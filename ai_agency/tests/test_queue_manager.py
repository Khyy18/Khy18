"""Tests for queue_manager module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch

from queue_manager import OrderQueue


@pytest.mark.asyncio
class TestQueueManager:
    """Test queue system."""

    async def test_enqueue_adds_item(self):
        """enqueue_order adds item to queue."""
        queue = OrderQueue(max_size=10, worker_count=1)
        result = await queue.enqueue_order(1, "rewrite", "test text", priority=1)
        assert result is None  # None means success
        stats = queue.get_queue_stats()
        assert stats["queue_size"] == 1

    async def test_priority_ordering(self):
        """Urgent items (priority=0) come before normal (priority=1)."""
        queue = OrderQueue(max_size=10, worker_count=1)
        await queue.enqueue_order(1, "rewrite", "normal text", priority=1)
        await queue.enqueue_order(2, "rewrite", "urgent text", priority=0)

        # Get items from queue - urgent should come first
        item = await queue._queue.get()
        assert item.order_id == 2  # urgent
        assert item.priority == 0

        item2 = await queue._queue.get()
        assert item2.order_id == 1  # normal
        assert item2.priority == 1

    async def test_queue_stats(self):
        """get_queue_stats returns correct values."""
        queue = OrderQueue(max_size=10, worker_count=2)
        await queue.enqueue_order(1, "rewrite", "text1", priority=1)
        await queue.enqueue_order(2, "seo", "text2", priority=1)

        stats = queue.get_queue_stats()
        assert stats["queue_size"] == 2
        assert stats["max_size"] == 10
        assert stats["worker_count"] == 2
        assert stats["total_processed"] == 0

    async def test_queue_full_returns_wait_time(self):
        """When queue is full, enqueue returns estimated wait time."""
        queue = OrderQueue(max_size=2, worker_count=1)
        await queue.enqueue_order(1, "rewrite", "text1", priority=1)
        await queue.enqueue_order(2, "rewrite", "text2", priority=1)

        # Queue is now full (max_size=2), next enqueue should return wait time
        result = await queue.enqueue_order(3, "rewrite", "text3", priority=1)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0

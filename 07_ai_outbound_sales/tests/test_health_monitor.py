"""Tests for the Health Monitor system."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.health_monitor import HealthMonitor, HealthReport


@pytest.fixture
def health_settings():
    """Create mock settings for health monitor."""
    s = MagicMock()
    s.redis_url = "redis://localhost:6379/0"
    s.telegram_bot_token = "test-token"
    s.telegram_chat_id = "test-chat"
    s.health_telegram_alerts = True
    return s


@pytest.fixture
def health_monitor(health_settings, session_factory):
    """Create a HealthMonitor instance for testing."""
    return HealthMonitor(settings=health_settings, session_factory=session_factory)


async def test_check_disk_space_returns_percentage(health_monitor):
    """Disk space check should return a float percentage."""
    result = health_monitor._check_disk_space()
    assert isinstance(result, float)
    assert 0.0 <= result <= 100.0


async def test_check_memory_returns_percentage(health_monitor):
    """Memory check should return a float percentage (0.0 if /proc/meminfo unavailable)."""
    result = health_monitor._check_memory()
    assert isinstance(result, float)
    assert 0.0 <= result <= 100.0


async def test_health_report_all_healthy():
    """A report with all checks passing should be marked all_healthy."""
    report = HealthReport(
        database_ok=True,
        redis_ok=True,
        disk_usage_percent=45.0,
        memory_usage_percent=60.0,
        issues=[],
        timestamp="2024-01-01T00:00:00+00:00",
    )
    assert report.all_healthy is True


async def test_health_report_with_issues():
    """A report with issues should not be marked all_healthy."""
    report = HealthReport(
        database_ok=True,
        redis_ok=False,
        disk_usage_percent=45.0,
        memory_usage_percent=60.0,
        issues=["Redis connection failed"],
        timestamp="2024-01-01T00:00:00+00:00",
    )
    assert report.all_healthy is False

    # Also test disk usage threshold
    report_disk = HealthReport(
        database_ok=True,
        redis_ok=True,
        disk_usage_percent=95.0,
        memory_usage_percent=60.0,
        issues=[],
        timestamp="2024-01-01T00:00:00+00:00",
    )
    assert report_disk.all_healthy is False


async def test_auto_recover_logs_warning_on_high_disk(health_monitor, caplog):
    """Auto-recover should log a warning when disk usage is above 90%."""
    import logging

    report = HealthReport(
        database_ok=True,
        redis_ok=True,
        disk_usage_percent=95.0,
        memory_usage_percent=60.0,
        issues=["Disk usage critical: 95.0%"],
        timestamp="2024-01-01T00:00:00+00:00",
    )

    with caplog.at_level(logging.WARNING):
        await health_monitor._auto_recover(report)

    assert "cleanup needed" in caplog.text.lower() or "Disk usage" in caplog.text


async def test_check_database_success(health_monitor):
    """Database check should succeed with a working session factory."""
    result = await health_monitor._check_database()
    assert result is True


async def test_check_redis_failure(health_monitor):
    """Redis check should return False when Redis is not available."""
    # In test environment there is no Redis, so it should fail gracefully
    result = await health_monitor._check_redis()
    assert result is False

"""Tests for channels/linkedin/proxy_manager.py - ProxyManager."""
from __future__ import annotations

import pytest

from channels.linkedin.proxy_manager import ProxyManager


def _make_pool(count: int = 3) -> list[dict]:
    """Create a test proxy pool."""
    return [
        {
            "url": f"http://proxy{i}.example.com:{8000 + i}",
            "username": f"user{i}",
            "password": f"pass{i}",
            "type": "residential",
            "health_score": 1.0,
            "last_used": None,
            "session_id": None,
        }
        for i in range(count)
    ]


class TestRoundRobinSelection:
    """Test round-robin proxy selection."""

    def test_round_robin_cycles_through_proxies(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        first = pm.get_proxy()
        second = pm.get_proxy()
        third = pm.get_proxy()
        fourth = pm.get_proxy()

        # Should cycle through proxies
        assert first["url"] == "http://proxy0.example.com:8000"
        assert second["url"] == "http://proxy1.example.com:8001"
        assert third["url"] == "http://proxy2.example.com:8002"
        # Wraps around
        assert fourth["url"] == "http://proxy0.example.com:8000"

    def test_get_proxy_returns_none_for_empty_pool(self):
        pm = ProxyManager(proxy_pool=[])
        result = pm.get_proxy()
        assert result is None

    def test_get_proxy_sets_last_used(self):
        pool = _make_pool(1)
        pm = ProxyManager(proxy_pool=pool)

        proxy = pm.get_proxy()
        assert proxy is not None
        assert proxy["last_used"] is not None


class TestStickySessions:
    """Test sticky session assignment."""

    def test_sticky_session_returns_same_proxy(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        first = pm.get_proxy(session_id="session_1")
        second = pm.get_proxy(session_id="session_1")

        assert first["url"] == second["url"]

    def test_different_sessions_can_get_different_proxies(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        proxy_a = pm.get_proxy(session_id="session_a")
        proxy_b = pm.get_proxy(session_id="session_b")

        # They may differ (round-robin moves forward)
        assert proxy_a is not None
        assert proxy_b is not None

    def test_release_proxy_removes_sticky_session(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        proxy = pm.get_proxy(session_id="session_1")
        pm.release_proxy("session_1")

        # After release, session_id is cleared
        assert proxy["session_id"] is None

    def test_release_nonexistent_session_is_noop(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)
        # Should not raise
        pm.release_proxy("nonexistent")


class TestHealthScoring:
    """Test health scoring - report_failure reduces, report_success increases."""

    def test_report_failure_decreases_health(self):
        pool = _make_pool(1)
        pm = ProxyManager(proxy_pool=pool)

        url = pool[0]["url"]
        pm.report_failure(url)

        assert pm.proxy_pool[0]["health_score"] == pytest.approx(0.8)

    def test_report_failure_minimum_is_zero(self):
        pool = _make_pool(1)
        pool[0]["health_score"] = 0.1
        pm = ProxyManager(proxy_pool=pool)

        url = pool[0]["url"]
        pm.report_failure(url)

        assert pm.proxy_pool[0]["health_score"] == 0.0

    def test_report_success_increases_health(self):
        pool = _make_pool(1)
        pool[0]["health_score"] = 0.5
        pm = ProxyManager(proxy_pool=pool)

        url = pool[0]["url"]
        pm.report_success(url)

        assert pm.proxy_pool[0]["health_score"] == pytest.approx(0.6)

    def test_report_success_maximum_is_one(self):
        pool = _make_pool(1)
        pool[0]["health_score"] = 0.95
        pm = ProxyManager(proxy_pool=pool)

        url = pool[0]["url"]
        pm.report_success(url)

        assert pm.proxy_pool[0]["health_score"] == 1.0

    def test_report_failure_unknown_url_is_noop(self):
        pool = _make_pool(1)
        pm = ProxyManager(proxy_pool=pool)
        pm.report_failure("http://unknown.example.com:9999")
        assert pm.proxy_pool[0]["health_score"] == 1.0


class TestGetHealthyProxies:
    """Test get_healthy_proxies filters out unhealthy proxies."""

    def test_all_healthy(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        healthy = pm.get_healthy_proxies()
        assert len(healthy) == 3

    def test_filters_unhealthy(self):
        pool = _make_pool(3)
        pool[0]["health_score"] = 0.2  # Below 0.3 threshold
        pool[1]["health_score"] = 0.3  # Exactly 0.3, not > 0.3
        pm = ProxyManager(proxy_pool=pool)

        healthy = pm.get_healthy_proxies()
        assert len(healthy) == 1
        assert healthy[0]["url"] == "http://proxy2.example.com:8002"

    def test_get_proxy_skips_unhealthy(self):
        pool = _make_pool(3)
        pool[0]["health_score"] = 0.0
        pool[1]["health_score"] = 0.0
        pm = ProxyManager(proxy_pool=pool)

        proxy = pm.get_proxy()
        assert proxy is not None
        assert proxy["url"] == "http://proxy2.example.com:8002"


class TestFingerprintGeneration:
    """Test fingerprint generation randomness."""

    def test_fingerprint_has_required_keys(self):
        fp = ProxyManager.generate_fingerprint()
        assert "user_agent" in fp
        assert "timezone" in fp
        assert "language" in fp
        assert "screen_resolution" in fp

    def test_screen_resolution_has_dimensions(self):
        fp = ProxyManager.generate_fingerprint()
        assert "width" in fp["screen_resolution"]
        assert "height" in fp["screen_resolution"]

    def test_fingerprints_vary(self):
        """Generate multiple fingerprints and check they are not all identical."""
        fingerprints = [ProxyManager.generate_fingerprint() for _ in range(20)]
        # At least some variation expected in user_agent or timezone
        user_agents = set(fp["user_agent"] for fp in fingerprints)
        assert len(user_agents) > 1


class TestRotationOnFailure:
    """Test rotation on failure."""

    def test_rotate_for_session_assigns_new_proxy(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        # Assign initial proxy
        original = pm.get_proxy(session_id="sess1")
        original_url = original["url"]

        # Force rotation
        rotated = pm.rotate_for_session("sess1")
        assert rotated is not None
        assert rotated["url"] != original_url

    def test_rotate_for_session_no_previous(self):
        pool = _make_pool(3)
        pm = ProxyManager(proxy_pool=pool)

        rotated = pm.rotate_for_session("new_session")
        assert rotated is not None

    def test_rotate_when_all_unhealthy_returns_none(self):
        pool = _make_pool(2)
        pool[0]["health_score"] = 0.0
        pool[1]["health_score"] = 0.0
        pm = ProxyManager(proxy_pool=pool)

        result = pm.rotate_for_session("sess1")
        assert result is None

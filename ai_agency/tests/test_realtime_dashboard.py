"""Tests for realtime_dashboard module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
class TestRealtimeDashboard:
    """Test realtime_dashboard module functionality."""

    async def test_broadcast_event_no_connections(self, initialized_db):
        """broadcast_event returns 0 when no connections."""
        import realtime_dashboard
        # Ensure no connections
        realtime_dashboard._ws_connections.clear()
        sent = await realtime_dashboard.broadcast_event("new_order", {"id": 1})
        assert sent == 0

    async def test_broadcast_event_structure(self, initialized_db):
        """broadcast_event sends correctly structured JSON."""
        import realtime_dashboard

        # Create mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        realtime_dashboard._ws_connections.add(mock_ws)

        try:
            sent = await realtime_dashboard.broadcast_event("payment", {"amount": 100})
            assert sent == 1
            # Verify the message structure
            call_args = mock_ws.send_str.call_args[0][0]
            message = json.loads(call_args)
            assert message["type"] == "payment"
            assert message["data"]["amount"] == 100
            assert "timestamp" in message
        finally:
            realtime_dashboard._ws_connections.clear()

    async def test_auth_token_validation(self, initialized_db):
        """_get_ws_auth_token returns config value."""
        import realtime_dashboard
        import config

        config.WS_AUTH_TOKEN = "test_secret_token"
        token = realtime_dashboard._get_ws_auth_token()
        assert token == "test_secret_token"
        config.WS_AUTH_TOKEN = ""

    async def test_get_live_counters(self, initialized_db):
        """_get_live_counters returns dict with expected keys."""
        import realtime_dashboard
        counters = await realtime_dashboard._get_live_counters()
        assert "revenue_today" in counters
        assert "orders_in_queue" in counters
        assert "active_clients" in counters

    async def test_connection_count(self, initialized_db):
        """get_connection_count reflects active connections."""
        import realtime_dashboard
        realtime_dashboard._ws_connections.clear()
        assert realtime_dashboard.get_connection_count() == 0

        mock_ws = AsyncMock()
        realtime_dashboard._ws_connections.add(mock_ws)
        assert realtime_dashboard.get_connection_count() == 1
        realtime_dashboard._ws_connections.clear()

    async def test_dead_connections_cleaned(self, initialized_db):
        """Dead connections are removed during broadcast."""
        import realtime_dashboard

        mock_ws = AsyncMock()
        mock_ws.closed = True  # Dead connection
        realtime_dashboard._ws_connections.add(mock_ws)

        sent = await realtime_dashboard.broadcast_event("test", {})
        assert sent == 0
        assert mock_ws not in realtime_dashboard._ws_connections
        realtime_dashboard._ws_connections.clear()

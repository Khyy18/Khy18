"""Тесты WebSocket endpoint."""

import pytest
from starlette.testclient import TestClient

from ai_office.api.main import app
from ai_office.api.websocket import broadcast_event, manager


@pytest.fixture
def sync_client():
    """Синхронный клиент для WebSocket тестов."""
    return TestClient(app)


def test_websocket_connect(sync_client):
    """Тест подключения к WebSocket."""
    with sync_client.websocket_connect("/api/ws") as websocket:
        assert websocket is not None


def test_websocket_receive_broadcast(sync_client):
    """Тест получения broadcast сообщения через WebSocket."""
    import asyncio

    with sync_client.websocket_connect("/api/ws") as websocket:
        # Отправляем broadcast
        asyncio.get_event_loop().run_until_complete(
            broadcast_event("new_task", {"id": 1, "description": "Test"})
        )
        data = websocket.receive_json()
        assert data["event"] == "new_task"
        assert data["data"]["id"] == 1
        assert data["data"]["description"] == "Test"


def test_websocket_multiple_clients(sync_client):
    """Тест broadcast нескольким клиентам."""
    import asyncio

    with sync_client.websocket_connect("/api/ws") as ws1:
        with sync_client.websocket_connect("/api/ws") as ws2:
            asyncio.get_event_loop().run_until_complete(
                broadcast_event("task_updated", {"id": 2, "status": "done"})
            )
            data1 = ws1.receive_json()
            data2 = ws2.receive_json()
            assert data1["event"] == "task_updated"
            assert data2["event"] == "task_updated"
            assert data1["data"]["id"] == 2


def test_connection_manager_disconnect():
    """Тест отключения из ConnectionManager."""
    # ConnectionManager.disconnect should handle missing connections gracefully
    from unittest.mock import MagicMock

    initial_count = sum(len(v) for v in manager.connections_by_tenant.values())
    fake_ws = MagicMock()
    manager.disconnect(fake_ws)  # should not raise
    final_count = sum(len(v) for v in manager.connections_by_tenant.values())
    assert final_count == initial_count

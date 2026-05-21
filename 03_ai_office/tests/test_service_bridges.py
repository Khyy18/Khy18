"""Тесты для API мостов к внешним сервисам (Zenith, Text Agency, Combo Bot)."""

import pytest


@pytest.mark.asyncio
async def test_zenith_service_offline(test_client):
    """Zenith endpoint returns offline status when service is unreachable."""
    resp = await test_client.get("/api/services/zenith")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "zenith_trading"
    assert data["status"] == "offline"
    assert data["health"] is None
    assert data["stats"] is None


@pytest.mark.asyncio
async def test_text_agency_service_offline(test_client):
    """Text Agency endpoint returns offline status when service is unreachable."""
    resp = await test_client.get("/api/services/text-agency")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "text_agency"
    assert data["status"] == "offline"
    assert data["health"] is None
    assert data["stats"] is None


@pytest.mark.asyncio
async def test_combo_bot_service_offline(test_client):
    """Combo Bot endpoint returns offline status when service is unreachable."""
    resp = await test_client.get("/api/services/combo-bot")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "combo_bot"
    assert data["status"] == "offline"
    assert data["health"] is None
    assert data["stats"] is None


@pytest.mark.asyncio
async def test_zenith_agent_config():
    """Zenith trading agent config is properly structured."""
    from ai_office.agents.zenith_trading import zenith_trading_config

    assert zenith_trading_config.name == "zenith_trading"
    assert zenith_trading_config.role == "Zenith Crypto Trading Integration"
    assert len(zenith_trading_config.tools) == 4
    tool_names = [t.name for t in zenith_trading_config.tools]
    assert "get_trading_stats" in tool_names
    assert "get_open_positions" in tool_names
    assert "get_pnl_summary" in tool_names
    assert "delegate_to_agent" in tool_names


@pytest.mark.asyncio
async def test_text_agency_agent_config():
    """Text agency agent config is properly structured."""
    from ai_office.agents.text_agency import text_agency_config

    assert text_agency_config.name == "text_agency"
    assert text_agency_config.role == "AI Text Agency Integration"
    assert len(text_agency_config.tools) == 4
    tool_names = [t.name for t in text_agency_config.tools]
    assert "get_content_stats" in tool_names
    assert "get_recent_articles" in tool_names
    assert "get_content_queue" in tool_names
    assert "delegate_to_agent" in tool_names


@pytest.mark.asyncio
async def test_combo_bot_agent_config():
    """Combo bot agent config is properly structured."""
    from ai_office.agents.combo_bot import combo_bot_config

    assert combo_bot_config.name == "combo_bot"
    assert combo_bot_config.role == "Combo Bot Integration"
    assert len(combo_bot_config.tools) == 4
    tool_names = [t.name for t in combo_bot_config.tools]
    assert "get_bot_status" in tool_names
    assert "get_active_users" in tool_names
    assert "get_command_stats" in tool_names
    assert "delegate_to_agent" in tool_names


@pytest.mark.asyncio
async def test_agents_registered_in_registry():
    """All new agents are registered in the global registry."""
    from ai_office.agents.registry import registry

    names = registry.get_names()
    assert "zenith_trading" in names
    assert "text_agency" in names
    assert "combo_bot" in names

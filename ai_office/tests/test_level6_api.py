"""Тесты для Level 6 API эндпоинтов."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_approval(test_client: AsyncClient):
    """Создание запроса на одобрение."""
    resp = await test_client.post(
        "/api/approvals?agent_name=Alice&action_type=deploy&description=Deploy+v2"
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_name"] == "Alice"
    assert data["action_type"] == "deploy"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_list_approvals(test_client: AsyncClient):
    """Список запросов на одобрение."""
    # Create one first
    await test_client.post(
        "/api/approvals?agent_name=Sam&action_type=delete&description=Delete+task"
    )
    resp = await test_client.get("/api/approvals")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_approval_by_id(test_client: AsyncClient):
    """Получение одного запроса по ID."""
    create_resp = await test_client.post(
        "/api/approvals?agent_name=Eva&action_type=budget&description=Over+budget"
    )
    request_id = create_resp.json()["id"]
    resp = await test_client.get(f"/api/approvals/{request_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == request_id


@pytest.mark.asyncio
async def test_resolve_approval(test_client: AsyncClient):
    """Разрешение запроса на одобрение."""
    create_resp = await test_client.post(
        "/api/approvals?agent_name=Alice&action_type=deploy&description=Deploy+v3"
    )
    request_id = create_resp.json()["id"]

    resp = await test_client.post(
        f"/api/approvals/{request_id}/resolve",
        json={"approved": True, "user_id": 42},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["resolved_by_user_id"] == 42


@pytest.mark.asyncio
async def test_sla_status(test_client: AsyncClient):
    """Получение статуса SLA."""
    resp = await test_client.get("/api/sla/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "compliance_percent" in data
    assert "avg_response_by_priority" in data
    assert "breaches_count" in data
    assert "total_monitored" in data


@pytest.mark.asyncio
async def test_analytics_overview(test_client: AsyncClient):
    """Обзор аналитики."""
    resp = await test_client.get("/api/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks_completed_week" in data
    assert "tasks_completed_month" in data
    assert "avg_time_to_resolve" in data
    assert "agent_workload" in data
    assert "throughput_trend" in data


@pytest.mark.asyncio
async def test_analytics_agent(test_client: AsyncClient, seed_data):
    """Аналитика по агенту."""
    resp = await test_client.get("/api/analytics/agents/Alice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_name"] == "Alice"
    assert "tasks_completed" in data
    assert "avg_response_time" in data
    assert "delegation_count" in data
    assert "sla_compliance_percent" in data


@pytest.mark.asyncio
async def test_analytics_agent_not_found(test_client: AsyncClient):
    """Аналитика по несуществующему агенту."""
    resp = await test_client.get("/api/analytics/agents/NonExistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analytics_productivity(test_client: AsyncClient):
    """Метрики продуктивности."""
    resp = await test_client.get("/api/analytics/productivity")
    assert resp.status_code == 200
    data = resp.json()
    assert "created_vs_completed" in data
    assert "peak_hours" in data
    assert "most_used_templates" in data


@pytest.mark.asyncio
async def test_audit_list(test_client: AsyncClient):
    """Список записей аудита."""
    resp = await test_client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_audit_export_csv(test_client: AsyncClient):
    """Экспорт аудита в CSV."""
    resp = await test_client.get("/api/audit/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_audit_export_json(test_client: AsyncClient):
    """Экспорт аудита в JSON."""
    resp = await test_client.get("/api/audit/export?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert "report_type" in data
    assert data["report_type"] == "audit_export"


@pytest.mark.asyncio
async def test_knowledge_add_and_query(test_client: AsyncClient):
    """Добавление и запрос фактов."""
    # Add a fact
    resp = await test_client.post(
        "/api/knowledge",
        json={
            "subject": "Python",
            "predicate": "используется_для",
            "object_value": "backend",
            "source_agent": "user",
            "confidence": 0.9,
        },
    )
    assert resp.status_code == 201
    fact_id = resp.json()["id"]
    assert resp.json()["subject"] == "Python"

    # Query by entity
    resp = await test_client.get("/api/knowledge?entity=Python")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(f["subject"] == "Python" for f in data)


@pytest.mark.asyncio
async def test_knowledge_delete(test_client: AsyncClient):
    """Удаление факта."""
    # Add a fact
    resp = await test_client.post(
        "/api/knowledge",
        json={
            "subject": "ToDelete",
            "predicate": "test",
            "object_value": "value",
        },
    )
    fact_id = resp.json()["id"]

    # Delete it
    resp = await test_client.delete(f"/api/knowledge/{fact_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify it's gone
    resp = await test_client.get("/api/knowledge?entity=ToDelete")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_branding_get(test_client: AsyncClient):
    """Получение конфигурации брендинга."""
    resp = await test_client.get("/api/branding")
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "AI Office"
    assert data["accent_color"] == "#3b82f6"


@pytest.mark.asyncio
async def test_branding_update(test_client: AsyncClient):
    """Обновление конфигурации брендинга."""
    resp = await test_client.patch(
        "/api/branding",
        json={"company_name": "My Company", "accent_color": "#ff0000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "My Company"
    assert data["accent_color"] == "#ff0000"

    # Verify persistence
    resp = await test_client.get("/api/branding")
    assert resp.status_code == 200
    assert resp.json()["company_name"] == "My Company"


@pytest.mark.asyncio
async def test_marketplace_list(test_client: AsyncClient):
    """Список плагинов маркетплейса."""
    resp = await test_client.get("/api/marketplace")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 5
    assert data[0]["id"] == "researcher"


@pytest.mark.asyncio
async def test_marketplace_install(test_client: AsyncClient):
    """Установка плагина."""
    resp = await test_client.post("/api/marketplace/install/translator")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "translator"
    assert data["installed"] is True


@pytest.mark.asyncio
async def test_marketplace_uninstall(test_client: AsyncClient):
    """Удаление плагина."""
    # Install first
    await test_client.post("/api/marketplace/install/translator")
    # Uninstall
    resp = await test_client.delete("/api/marketplace/translator")
    assert resp.status_code == 200
    assert resp.json()["status"] == "uninstalled"


@pytest.mark.asyncio
async def test_marketplace_install_not_found(test_client: AsyncClient):
    """Установка несуществующего плагина."""
    resp = await test_client.post("/api/marketplace/install/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_marketplace_uninstall_not_installed(test_client: AsyncClient):
    """Удаление неустановленного плагина."""
    resp = await test_client.delete("/api/marketplace/nonexistent")
    assert resp.status_code == 404

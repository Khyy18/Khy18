"""Tests for tenant isolation in routes."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_office.api.auth import create_access_token, hash_password
from ai_office.api.main import app
from ai_office.core.database import Base, get_session
from ai_office.core.models import (
    ActivityLog,
    Agent,
    Plan,
    PlanStep,
    Task,
    Tenant,
    TenantAgent,
    User,
)


@pytest_asyncio.fixture
async def isolation_session():
    """Async session for tenant isolation tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def isolation_client(isolation_session: AsyncSession):
    """HTTP client with overridden session for isolation tests."""

    async def override_get_session():
        yield isolation_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def two_tenants(isolation_session: AsyncSession):
    """Create two tenants with users and return auth headers for each."""
    # Tenant A
    tenant_a = Tenant(name="Company A", email="admin@a.com", plan_name="trial")
    isolation_session.add(tenant_a)
    await isolation_session.flush()

    user_a = User(
        tenant_id=tenant_a.id,
        email="user@a.com",
        password_hash=hash_password("pass_a"),
        role="admin",
    )
    isolation_session.add(user_a)
    await isolation_session.flush()

    # Tenant B
    tenant_b = Tenant(name="Company B", email="admin@b.com", plan_name="trial")
    isolation_session.add(tenant_b)
    await isolation_session.flush()

    user_b = User(
        tenant_id=tenant_b.id,
        email="user@b.com",
        password_hash=hash_password("pass_b"),
        role="admin",
    )
    isolation_session.add(user_b)
    await isolation_session.flush()

    # Create an agent for activity log tests
    agent = Agent(
        name="TestAgent",
        role="Test",
        system_prompt="test",
        status="idle",
    )
    isolation_session.add(agent)
    await isolation_session.commit()
    await isolation_session.refresh(user_a)
    await isolation_session.refresh(user_b)
    await isolation_session.refresh(tenant_a)
    await isolation_session.refresh(tenant_b)
    await isolation_session.refresh(agent)

    token_a = create_access_token({"sub": user_a.id, "tenant_id": tenant_a.id})
    token_b = create_access_token({"sub": user_b.id, "tenant_id": tenant_b.id})

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "user_a": user_a,
        "user_b": user_b,
        "headers_a": headers_a,
        "headers_b": headers_b,
        "agent": agent,
    }


@pytest.mark.asyncio
async def test_task_isolation(isolation_client: AsyncClient, two_tenants: dict):
    """Tenant A cannot see Tenant B's tasks and vice versa."""
    headers_a = two_tenants["headers_a"]
    headers_b = two_tenants["headers_b"]

    # Create task as tenant A
    resp = await isolation_client.post(
        "/api/tasks",
        json={"description": "Task for A", "priority": "high"},
        headers=headers_a,
    )
    assert resp.status_code == 201
    task_a_id = resp.json()["id"]

    # Create task as tenant B
    resp = await isolation_client.post(
        "/api/tasks",
        json={"description": "Task for B", "priority": "low"},
        headers=headers_b,
    )
    assert resp.status_code == 201
    task_b_id = resp.json()["id"]

    # Tenant A sees only their task
    resp = await isolation_client.get("/api/tasks", headers=headers_a)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == task_a_id
    assert items[0]["description"] == "Task for A"

    # Tenant B sees only their task
    resp = await isolation_client.get("/api/tasks", headers=headers_b)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == task_b_id
    assert items[0]["description"] == "Task for B"


@pytest.mark.asyncio
async def test_activity_isolation(
    isolation_client: AsyncClient,
    isolation_session: AsyncSession,
    two_tenants: dict,
):
    """Activity logs are scoped per tenant."""
    headers_a = two_tenants["headers_a"]
    headers_b = two_tenants["headers_b"]
    agent = two_tenants["agent"]
    tenant_a = two_tenants["tenant_a"]
    tenant_b = two_tenants["tenant_b"]

    # Create activity logs for each tenant
    log_a = ActivityLog(
        agent_id=agent.id,
        action_type="task_created",
        action_description="Activity for A",
        tenant_id=tenant_a.id,
    )
    log_b = ActivityLog(
        agent_id=agent.id,
        action_type="task_created",
        action_description="Activity for B",
        tenant_id=tenant_b.id,
    )
    isolation_session.add_all([log_a, log_b])
    await isolation_session.commit()

    # Tenant A sees only their activity
    resp = await isolation_client.get("/api/activity", headers=headers_a)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["action_description"] == "Activity for A"

    # Tenant B sees only their activity
    resp = await isolation_client.get("/api/activity", headers=headers_b)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["action_description"] == "Activity for B"


@pytest.mark.asyncio
async def test_plans_isolation(
    isolation_client: AsyncClient,
    isolation_session: AsyncSession,
    two_tenants: dict,
):
    """Plans are scoped per tenant."""
    headers_a = two_tenants["headers_a"]
    headers_b = two_tenants["headers_b"]
    tenant_a = two_tenants["tenant_a"]
    tenant_b = two_tenants["tenant_b"]

    # Create plans for each tenant
    plan_a = Plan(goal="Plan for A", status="active", tenant_id=tenant_a.id)
    plan_b = Plan(goal="Plan for B", status="active", tenant_id=tenant_b.id)
    isolation_session.add_all([plan_a, plan_b])
    await isolation_session.commit()
    await isolation_session.refresh(plan_a)
    await isolation_session.refresh(plan_b)

    # Tenant A sees only their plan
    resp = await isolation_client.get("/api/plans", headers=headers_a)
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) == 1
    assert plans[0]["goal"] == "Plan for A"

    # Tenant B sees only their plan
    resp = await isolation_client.get("/api/plans", headers=headers_b)
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) == 1
    assert plans[0]["goal"] == "Plan for B"

    # Tenant A cannot get Tenant B's plan by ID
    resp = await isolation_client.get(f"/api/plans/{plan_b.id}", headers=headers_a)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delegations_isolation(
    isolation_client: AsyncClient,
    isolation_session: AsyncSession,
    two_tenants: dict,
):
    """Delegations are scoped per tenant."""
    headers_a = two_tenants["headers_a"]
    headers_b = two_tenants["headers_b"]
    agent = two_tenants["agent"]
    tenant_a = two_tenants["tenant_a"]
    tenant_b = two_tenants["tenant_b"]

    # Create delegation logs for each tenant
    del_a = ActivityLog(
        agent_id=agent.id,
        action_type="task_delegated",
        action_description="Delegation A",
        tenant_id=tenant_a.id,
    )
    del_b = ActivityLog(
        agent_id=agent.id,
        action_type="task_delegated",
        action_description="Delegation B",
        tenant_id=tenant_b.id,
    )
    isolation_session.add_all([del_a, del_b])
    await isolation_session.commit()

    # Tenant A sees only their delegation
    resp = await isolation_client.get("/api/delegations", headers=headers_a)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["action_description"] == "Delegation A"

    # Tenant B sees only their delegation
    resp = await isolation_client.get("/api/delegations", headers=headers_b)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["action_description"] == "Delegation B"


@pytest.mark.asyncio
async def test_no_auth_backward_compat(
    isolation_client: AsyncClient,
    isolation_session: AsyncSession,
    two_tenants: dict,
):
    """Without auth headers, all data is visible (backward compat)."""
    tenant_a = two_tenants["tenant_a"]
    tenant_b = two_tenants["tenant_b"]
    headers_a = two_tenants["headers_a"]
    headers_b = two_tenants["headers_b"]

    # Create tasks for both tenants
    await isolation_client.post(
        "/api/tasks",
        json={"description": "Task A", "priority": "high"},
        headers=headers_a,
    )
    await isolation_client.post(
        "/api/tasks",
        json={"description": "Task B", "priority": "low"},
        headers=headers_b,
    )

    # Without auth, see all tasks (no tenant filter)
    resp = await isolation_client.get("/api/tasks")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2


@pytest.mark.asyncio
async def test_agents_tenant_scoping(
    isolation_client: AsyncClient,
    isolation_session: AsyncSession,
    two_tenants: dict,
):
    """When tenant has TenantAgent records, only enabled agents are visible."""
    headers_a = two_tenants["headers_a"]
    tenant_a = two_tenants["tenant_a"]
    agent = two_tenants["agent"]

    # Create another agent
    agent2 = Agent(
        name="OtherAgent", role="Other", system_prompt="other", status="idle"
    )
    isolation_session.add(agent2)
    await isolation_session.flush()

    # Enable only TestAgent for tenant A
    ta = TenantAgent(
        tenant_id=tenant_a.id, agent_name="TestAgent", is_enabled=True
    )
    isolation_session.add(ta)
    await isolation_session.commit()

    # Tenant A sees only TestAgent
    resp = await isolation_client.get("/api/agents", headers=headers_a)
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["name"] == "TestAgent"

    # Without auth, see all agents
    resp = await isolation_client.get("/api/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 2

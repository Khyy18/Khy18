"""Тесты ApprovalManager - создание, проверка и обработка запросов."""

import asyncio

import pytest
from sqlalchemy import select

from ai_office.core.approval import ApprovalManager, requires_approval
from ai_office.core.models import ApprovalRequest


@pytest.mark.asyncio
async def test_request_approval_creates_record(async_session):
    """Тест создания запроса на одобрение в БД."""
    manager = ApprovalManager()
    request_id = await manager.request_approval(
        session=async_session,
        agent_name="Sam",
        action_type="deploy",
        description="Deploy to production",
        metadata={"version": "1.2.3"},
    )

    assert request_id is not None
    result = await async_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    request = result.scalar_one()
    assert request.agent_name == "Sam"
    assert request.action_type == "deploy"
    assert request.description == "Deploy to production"
    assert request.status == "pending"
    assert request.metadata_json is not None
    assert "1.2.3" in request.metadata_json


@pytest.mark.asyncio
async def test_check_approval_pending(async_session):
    """Тест проверки статуса pending."""
    manager = ApprovalManager()
    request_id = await manager.request_approval(
        session=async_session,
        agent_name="Nova",
        action_type="deploy",
        description="Deploy service",
    )

    status = await manager.check_approval(async_session, request_id)
    assert status == "pending"


@pytest.mark.asyncio
async def test_handle_callback_approve(async_session):
    """Тест одобрения запроса через callback."""
    manager = ApprovalManager()
    request_id = await manager.request_approval(
        session=async_session,
        agent_name="Sam",
        action_type="delete_task",
        description="Delete task #5",
    )

    await manager.handle_callback(
        session=async_session,
        request_id=request_id,
        approved=True,
        user_id=12345,
    )

    status = await manager.check_approval(async_session, request_id)
    assert status == "approved"

    result = await async_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    request = result.scalar_one()
    assert request.resolved_by_user_id == 12345
    assert request.resolved_at is not None


@pytest.mark.asyncio
async def test_handle_callback_reject(async_session):
    """Тест отклонения запроса через callback."""
    manager = ApprovalManager()
    request_id = await manager.request_approval(
        session=async_session,
        agent_name="Alice",
        action_type="grant_permissions",
        description="Grant admin to user",
    )

    await manager.handle_callback(
        session=async_session,
        request_id=request_id,
        approved=False,
        user_id=67890,
    )

    status = await manager.check_approval(async_session, request_id)
    assert status == "rejected"


@pytest.mark.asyncio
async def test_wait_for_approval_approved(async_session):
    """Тест ожидания одобрения - положительный результат."""
    manager = ApprovalManager()
    request_id = await manager.request_approval(
        session=async_session,
        agent_name="Sam",
        action_type="deploy",
        description="Deploy v2",
    )

    # Simulate approval after a short delay
    async def approve_after_delay():
        await asyncio.sleep(0.1)
        await manager.handle_callback(
            session=async_session,
            request_id=request_id,
            approved=True,
            user_id=111,
        )

    asyncio.create_task(approve_after_delay())
    result = await manager.wait_for_approval(request_id)
    assert result is True


@pytest.mark.asyncio
async def test_wait_for_approval_timeout(async_session):
    """Тест таймаута ожидания одобрения."""
    manager = ApprovalManager()
    manager.TIMEOUT_SECONDS = 0.2  # Short timeout for test

    request_id = await manager.request_approval(
        session=async_session,
        agent_name="Nova",
        action_type="deploy",
        description="Deploy without response",
    )

    result = await manager.wait_for_approval(request_id)
    assert result is False


@pytest.mark.asyncio
async def test_requires_approval_decorator_approved(async_session):
    """Тест декоратора @requires_approval - одобрено."""
    manager = ApprovalManager()
    manager.TIMEOUT_SECONDS = 2

    # Monkey-patch the module-level instance
    import ai_office.core.approval as approval_mod
    original = approval_mod.approval_manager
    approval_mod.approval_manager = manager

    call_count = 0

    @requires_approval("deploy")
    async def deploy_action(session, agent_name="Sam", description="Deploy"):
        nonlocal call_count
        call_count += 1
        return "deployed"

    # Approve in background
    async def approve_soon():
        await asyncio.sleep(0.1)
        # Get the request_id from the manager's events
        for rid in list(manager._events.keys()):
            await manager.handle_callback(
                session=async_session,
                request_id=rid,
                approved=True,
                user_id=999,
            )

    asyncio.create_task(approve_soon())
    result = await deploy_action(async_session, agent_name="Sam", description="Deploy v3")
    assert result == "deployed"
    assert call_count == 1

    approval_mod.approval_manager = original


@pytest.mark.asyncio
async def test_requires_approval_decorator_rejected(async_session):
    """Тест декоратора @requires_approval - таймаут/отклонение."""
    manager = ApprovalManager()
    manager.TIMEOUT_SECONDS = 0.2

    import ai_office.core.approval as approval_mod
    original = approval_mod.approval_manager
    approval_mod.approval_manager = manager

    @requires_approval("deploy")
    async def deploy_action(session, agent_name="Sam", description="Deploy"):
        return "deployed"

    with pytest.raises(RuntimeError, match="not approved"):
        await deploy_action(async_session, agent_name="Sam", description="Deploy v4")

    approval_mod.approval_manager = original

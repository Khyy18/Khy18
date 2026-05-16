"""Тесты AuditLogger - создание записей, фильтрация."""

import json

import pytest
from sqlalchemy import select

from ai_office.core.audit import (
    AuditLogger,
    audit_task_action,
    audit_permission_change,
    audit_settings_change,
    audit_approval_decision,
)
from ai_office.core.models import AuditEntry


@pytest.mark.asyncio
async def test_audit_log_creates_entry(async_session):
    """Тест создания записи аудита."""
    logger = AuditLogger()
    entry = await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="user",
        actor_id="user_123",
        action="create_task",
        resource_type="task",
        resource_id="42",
        details={"priority": "high"},
        ip_address="192.168.1.1",
    )

    assert entry.id is not None
    assert entry.actor_type == "user"
    assert entry.actor_id == "user_123"
    assert entry.action == "create_task"
    assert entry.resource_type == "task"
    assert entry.resource_id == "42"
    assert entry.ip_address == "192.168.1.1"

    details = json.loads(entry.details_json)
    assert details["priority"] == "high"


@pytest.mark.asyncio
async def test_audit_log_without_optional_fields(async_session):
    """Тест создания записи аудита без опциональных полей."""
    logger = AuditLogger()
    entry = await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="agent",
        actor_id="alice",
        action="process_message",
        resource_type="message",
    )

    assert entry.id is not None
    assert entry.resource_id is None
    assert entry.details_json is None
    assert entry.ip_address is None


@pytest.mark.asyncio
async def test_audit_log_multiple_entries(async_session):
    """Тест создания нескольких записей аудита."""
    logger = AuditLogger()

    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="user",
        actor_id="user_1",
        action="login",
        resource_type="session",
    )
    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="agent",
        actor_id="sam",
        action="code_review",
        resource_type="pull_request",
        resource_id="PR-15",
    )
    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="system",
        actor_id="scheduler",
        action="cleanup",
        resource_type="cache",
    )

    result = await async_session.execute(select(AuditEntry))
    entries = result.scalars().all()
    assert len(entries) == 3


@pytest.mark.asyncio
async def test_audit_filter_by_actor(async_session):
    """Тест фильтрации записей аудита по actor_type."""
    logger = AuditLogger()

    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="user",
        actor_id="user_1",
        action="login",
        resource_type="session",
    )
    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="agent",
        actor_id="alice",
        action="respond",
        resource_type="message",
    )

    result = await async_session.execute(
        select(AuditEntry).where(AuditEntry.actor_type == "agent")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].actor_id == "alice"


@pytest.mark.asyncio
async def test_audit_filter_by_action(async_session):
    """Тест фильтрации записей аудита по action."""
    logger = AuditLogger()

    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="user",
        actor_id="user_1",
        action="create_task",
        resource_type="task",
    )
    await logger.log(
        session=async_session,
        workspace_id=None,
        actor_type="user",
        actor_id="user_1",
        action="delete_task",
        resource_type="task",
    )

    result = await async_session.execute(
        select(AuditEntry).where(AuditEntry.action == "delete_task")
    )
    entries = result.scalars().all()
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_audit_task_action_convenience(async_session):
    """Тест convenience-функции audit_task_action."""
    entry = await audit_task_action(
        session=async_session,
        workspace_id=None,
        actor_type="agent",
        actor_id="sam",
        action="complete_task",
        task_id=7,
        details={"duration_seconds": 120},
    )

    assert entry.resource_type == "task"
    assert entry.resource_id == "7"
    assert entry.action == "complete_task"


@pytest.mark.asyncio
async def test_audit_permission_change_convenience(async_session):
    """Тест convenience-функции audit_permission_change."""
    entry = await audit_permission_change(
        session=async_session,
        workspace_id=None,
        actor_id="owner_1",
        target_user_id="user_5",
        new_role="admin",
    )

    assert entry.action == "permission_change"
    assert entry.resource_type == "user"
    assert entry.resource_id == "user_5"
    details = json.loads(entry.details_json)
    assert details["new_role"] == "admin"


@pytest.mark.asyncio
async def test_audit_settings_change_convenience(async_session):
    """Тест convenience-функции audit_settings_change."""
    entry = await audit_settings_change(
        session=async_session,
        workspace_id=None,
        actor_type="user",
        actor_id="admin_1",
        setting_key="enable_proactive",
        details={"old_value": False, "new_value": True},
    )

    assert entry.action == "settings_change"
    assert entry.resource_type == "settings"
    assert entry.resource_id == "enable_proactive"


@pytest.mark.asyncio
async def test_audit_approval_decision_convenience(async_session):
    """Тест convenience-функции audit_approval_decision."""
    entry = await audit_approval_decision(
        session=async_session,
        workspace_id=None,
        user_id=12345,
        request_id=1,
        approved=True,
    )

    assert entry.action == "approved"
    assert entry.resource_type == "approval_request"
    assert entry.resource_id == "1"
    assert entry.actor_id == "12345"

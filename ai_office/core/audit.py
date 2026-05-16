"""Audit logging для compliance и отслеживания действий."""

import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import AuditEntry

logger = logging.getLogger(__name__)


class AuditLogger:
    """Логгер аудита для записи всех действий в системе."""

    async def log(
        self,
        session: AsyncSession,
        workspace_id: Optional[int],
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuditEntry:
        """Create an AuditEntry in the database.

        Args:
            session: Database session
            workspace_id: Workspace ID (nullable)
            actor_type: Type of actor ('user', 'agent', 'system')
            actor_id: Identifier of the actor
            action: Action performed
            resource_type: Type of resource affected
            resource_id: ID of the resource (optional)
            details: Additional details as dict (optional)
            ip_address: IP address of the actor (optional)

        Returns:
            Created AuditEntry instance
        """
        details_json = json.dumps(details, ensure_ascii=False) if details else None

        entry = AuditEntry(
            workspace_id=workspace_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details_json=details_json,
            ip_address=ip_address,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        logger.debug(
            "Audit: %s %s %s %s (resource=%s/%s)",
            actor_type,
            actor_id,
            action,
            resource_type,
            resource_type,
            resource_id,
        )
        return entry


# Module-level instance
audit_logger = AuditLogger()


async def audit_task_action(
    session: AsyncSession,
    workspace_id: Optional[int],
    actor_type: str,
    actor_id: str,
    action: str,
    task_id: int,
    details: Optional[dict] = None,
) -> AuditEntry:
    """Convenience function to audit task-related actions."""
    return await audit_logger.log(
        session=session,
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type="task",
        resource_id=str(task_id),
        details=details,
    )


async def audit_permission_change(
    session: AsyncSession,
    workspace_id: Optional[int],
    actor_id: str,
    target_user_id: str,
    new_role: str,
    details: Optional[dict] = None,
) -> AuditEntry:
    """Convenience function to audit permission changes."""
    return await audit_logger.log(
        session=session,
        workspace_id=workspace_id,
        actor_type="user",
        actor_id=actor_id,
        action="permission_change",
        resource_type="user",
        resource_id=target_user_id,
        details=details or {"new_role": new_role},
    )


async def audit_settings_change(
    session: AsyncSession,
    workspace_id: Optional[int],
    actor_type: str,
    actor_id: str,
    setting_key: str,
    details: Optional[dict] = None,
) -> AuditEntry:
    """Convenience function to audit settings changes."""
    return await audit_logger.log(
        session=session,
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="settings_change",
        resource_type="settings",
        resource_id=setting_key,
        details=details,
    )


async def audit_approval_decision(
    session: AsyncSession,
    workspace_id: Optional[int],
    user_id: int,
    request_id: int,
    approved: bool,
    details: Optional[dict] = None,
) -> AuditEntry:
    """Convenience function to audit approval decisions."""
    return await audit_logger.log(
        session=session,
        workspace_id=workspace_id,
        actor_type="user",
        actor_id=str(user_id),
        action="approved" if approved else "rejected",
        resource_type="approval_request",
        resource_id=str(request_id),
        details=details,
    )

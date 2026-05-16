"""Human-in-the-Loop Approval Workflow для критических действий."""

import asyncio
import functools
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import ApprovalRequest

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Менеджер запросов на одобрение критических действий."""

    APPROVAL_REQUIRED_ACTIONS = [
        "deploy",
        "budget_exceeded",
        "delete_task",
        "grant_permissions",
    ]
    TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self):
        self._events: dict[int, asyncio.Event] = {}
        self._results: dict[int, bool] = {}

    async def request_approval(
        self,
        session: AsyncSession,
        agent_name: str,
        action_type: str,
        description: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """Create an ApprovalRequest in DB and return request_id."""
        metadata_json = json.dumps(metadata) if metadata else None
        request = ApprovalRequest(
            agent_name=agent_name,
            action_type=action_type,
            description=description,
            metadata_json=metadata_json,
            status="pending",
        )
        session.add(request)
        await session.commit()
        await session.refresh(request)

        # Create an event for this request
        self._events[request.id] = asyncio.Event()
        logger.info(
            "Approval request #%d created: %s by %s",
            request.id,
            action_type,
            agent_name,
        )
        return request.id

    async def check_approval(self, session: AsyncSession, request_id: int) -> str:
        """Returns 'pending', 'approved', or 'rejected'."""
        result = await session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request is None:
            return "pending"
        return request.status

    async def handle_callback(
        self,
        session: AsyncSession,
        request_id: int,
        approved: bool,
        user_id: int,
    ) -> None:
        """Update DB status and notify waiting agent."""
        result = await session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        if request is None:
            logger.warning("Approval request #%d not found", request_id)
            return

        request.status = "approved" if approved else "rejected"
        request.resolved_at = datetime.now(timezone.utc)
        request.resolved_by_user_id = user_id
        await session.commit()

        # Store result and notify waiting coroutine
        self._results[request_id] = approved
        event = self._events.get(request_id)
        if event:
            event.set()

        logger.info(
            "Approval request #%d %s by user %d",
            request_id,
            request.status,
            user_id,
        )

    async def wait_for_approval(self, request_id: int) -> bool:
        """Wait on asyncio.Event with timeout, return True if approved."""
        event = self._events.get(request_id)
        if event is None:
            return False

        try:
            await asyncio.wait_for(event.wait(), timeout=self.TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning("Approval request #%d timed out", request_id)
            # Clean up
            self._events.pop(request_id, None)
            self._results.pop(request_id, None)
            return False

        approved = self._results.pop(request_id, False)
        self._events.pop(request_id, None)
        return approved


# Module-level instance
approval_manager = ApprovalManager()


def requires_approval(action_type: str):
    """Decorator that pauses tool execution until human approves.

    Wraps async tool functions. Creates an approval request, waits for response.
    If timeout or rejected, raises RuntimeError.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract session from kwargs or first arg
            session = kwargs.get("session")
            if session is None and args:
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        session = arg
                        break

            if session is None:
                raise RuntimeError("No database session available for approval request")

            agent_name = kwargs.get("agent_name", "unknown")
            description = kwargs.get("description", f"Action: {action_type}")

            request_id = await approval_manager.request_approval(
                session=session,
                agent_name=agent_name,
                action_type=action_type,
                description=description,
            )

            approved = await approval_manager.wait_for_approval(request_id)
            if not approved:
                raise RuntimeError(
                    f"Action '{action_type}' was not approved (request #{request_id})"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator

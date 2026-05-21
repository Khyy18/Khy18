"""Approval Queue - human-in-the-loop approval for high-value lead responses."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    ApprovalStatus,
    Lead,
    Message,
    PendingApproval,
)
from dashboard.auth import get_current_user
from core.models import User

logger = logging.getLogger(__name__)


class EmailSenderProtocol(Protocol):
    """Protocol for email sender dependency."""

    async def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        message_id: str,
        tracking_pixel_url: str | None = None,
        tracked_links: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        ...


# Module-level email sender reference, set during app startup
_email_sender: EmailSenderProtocol | None = None


def set_email_sender(sender: EmailSenderProtocol | None) -> None:
    """Set the module-level email sender used by ApprovalQueue to dispatch approved emails."""
    global _email_sender
    _email_sender = sender


def get_email_sender() -> EmailSenderProtocol | None:
    """Get the module-level email sender."""
    return _email_sender

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ---------- Schemas ----------

class ApprovalResponse(BaseModel):
    """Schema for approval list items."""
    id: str
    lead_id: str
    message_id: str | None
    proposed_response: dict[str, Any]
    status: str
    reviewer_notes: str | None
    created_at: str
    reviewed_at: str | None


class ApprovalActionRequest(BaseModel):
    """Schema for approve/reject actions."""
    reviewer_notes: str | None = None


class ApprovalEditRequest(BaseModel):
    """Schema for edit-and-send action."""
    subject: str
    body: str
    action: str = "send_reply"


# ---------- Helper ----------

async def _get_session() -> AsyncGenerator[AsyncSession, None]:
    """Lazy wrapper around core.db.get_session to avoid import-time engine creation."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


# ---------- ApprovalQueue class ----------

class ApprovalQueue:
    """Manages the pending approval workflow for high-value responses."""

    @staticmethod
    async def create_approval(
        session: AsyncSession,
        lead_id: uuid.UUID,
        message_id: uuid.UUID | None,
        proposed_response: dict[str, Any],
    ) -> PendingApproval:
        """Create a new pending approval entry.

        Args:
            session: The database session.
            lead_id: UUID of the lead.
            message_id: UUID of the inbound message (optional).
            proposed_response: The AI-generated response dict (subject, body, action).

        Returns:
            The created PendingApproval instance.
        """
        approval = PendingApproval(
            lead_id=lead_id,
            message_id=message_id,
            proposed_response=proposed_response,
            status=ApprovalStatus.pending,
        )
        session.add(approval)
        await session.flush()
        logger.info("Created pending approval %s for lead %s", approval.id, lead_id)
        return approval

    @staticmethod
    async def list_pending(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PendingApproval]:
        """List pending approvals for a tenant.

        Args:
            session: The database session.
            tenant_id: UUID of the tenant for isolation.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of PendingApproval instances.
        """
        stmt = (
            select(PendingApproval)
            .join(Lead, PendingApproval.lead_id == Lead.id)
            .where(Lead.tenant_id == tenant_id)
            .where(PendingApproval.status == ApprovalStatus.pending)
            .order_by(PendingApproval.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def approve(
        session: AsyncSession,
        approval_id: uuid.UUID,
        reviewer_notes: str | None = None,
    ) -> PendingApproval:
        """Approve a pending response and send it.

        Args:
            session: The database session.
            approval_id: UUID of the pending approval.
            reviewer_notes: Optional notes from the reviewer.

        Returns:
            The updated PendingApproval instance.
        """
        stmt = select(PendingApproval).where(PendingApproval.id == approval_id)
        result = await session.execute(stmt)
        approval = result.scalar_one_or_none()

        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")

        if approval.status != ApprovalStatus.pending:
            raise ValueError(f"Approval {approval_id} is not in pending status")

        approval.status = ApprovalStatus.approved
        approval.reviewer_notes = reviewer_notes
        approval.reviewed_at = datetime.now(timezone.utc)

        await session.flush()

        # Send the approved email to the lead
        await ApprovalQueue._send_approved_email(session, approval)

        logger.info("Approved approval %s", approval_id)
        return approval

    @staticmethod
    async def reject(
        session: AsyncSession,
        approval_id: uuid.UUID,
        reviewer_notes: str | None = None,
    ) -> PendingApproval:
        """Reject a pending response.

        Args:
            session: The database session.
            approval_id: UUID of the pending approval.
            reviewer_notes: Optional notes from the reviewer.

        Returns:
            The updated PendingApproval instance.
        """
        stmt = select(PendingApproval).where(PendingApproval.id == approval_id)
        result = await session.execute(stmt)
        approval = result.scalar_one_or_none()

        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")

        if approval.status != ApprovalStatus.pending:
            raise ValueError(f"Approval {approval_id} is not in pending status")

        approval.status = ApprovalStatus.rejected
        approval.reviewer_notes = reviewer_notes
        approval.reviewed_at = datetime.now(timezone.utc)

        await session.flush()
        logger.info("Rejected approval %s", approval_id)
        return approval

    @staticmethod
    async def edit_and_send(
        session: AsyncSession,
        approval_id: uuid.UUID,
        edited_response: dict[str, Any],
    ) -> PendingApproval:
        """Edit the proposed response, mark as approved, and send it.

        Args:
            session: The database session.
            approval_id: UUID of the pending approval.
            edited_response: The edited response dict (subject, body, action).

        Returns:
            The updated PendingApproval instance.
        """
        stmt = select(PendingApproval).where(PendingApproval.id == approval_id)
        result = await session.execute(stmt)
        approval = result.scalar_one_or_none()

        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")

        if approval.status != ApprovalStatus.pending:
            raise ValueError(f"Approval {approval_id} is not in pending status")

        approval.proposed_response = edited_response
        approval.status = ApprovalStatus.approved
        approval.reviewed_at = datetime.now(timezone.utc)

        await session.flush()

        # Send the edited email to the lead
        await ApprovalQueue._send_approved_email(session, approval)

        logger.info("Edited and approved approval %s", approval_id)
        return approval

    @staticmethod
    async def _send_approved_email(
        session: AsyncSession,
        approval: PendingApproval,
    ) -> None:
        """Send the approved response email to the lead.

        Args:
            session: The database session.
            approval: The approved PendingApproval instance.
        """
        sender = get_email_sender()
        if sender is None:
            logger.warning(
                "Email sender not configured, cannot send approved response for approval %s",
                approval.id,
            )
            return

        # Fetch the lead's email
        stmt = select(Lead).where(Lead.id == approval.lead_id)
        result = await session.execute(stmt)
        lead = result.scalar_one_or_none()

        if lead is None:
            logger.error("Lead %s not found for approval %s", approval.lead_id, approval.id)
            return

        proposed = approval.proposed_response
        subject = proposed.get("subject", "")
        body = proposed.get("body", "")
        message_id = str(approval.id)

        send_result = await sender.send_email(
            to=lead.email,
            subject=subject,
            html_body=body,
            message_id=message_id,
        )

        if send_result.get("success"):
            logger.info(
                "Approved email sent to %s for approval %s",
                lead.email,
                approval.id,
            )
        else:
            logger.error(
                "Failed to send approved email to %s for approval %s",
                lead.email,
                approval.id,
            )


# ---------- API Endpoints ----------

def _serialize_approval(approval: PendingApproval) -> dict[str, Any]:
    """Serialize a PendingApproval instance to a response dict."""
    return {
        "id": str(approval.id),
        "lead_id": str(approval.lead_id),
        "message_id": str(approval.message_id) if approval.message_id else None,
        "proposed_response": approval.proposed_response,
        "status": approval.status.value if approval.status else "pending",
        "reviewer_notes": approval.reviewer_notes,
        "created_at": approval.created_at.isoformat() if approval.created_at else None,
        "reviewed_at": approval.reviewed_at.isoformat() if approval.reviewed_at else None,
    }


@router.get("")
async def list_approvals(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[dict[str, Any]]:
    """List pending approvals for the current user's tenant."""
    approvals = await ApprovalQueue.list_pending(
        session=session,
        tenant_id=current_user.tenant_id,
        limit=limit,
        offset=offset,
    )
    return [_serialize_approval(a) for a in approvals]


@router.post("/{approval_id}/approve")
async def approve_response(
    approval_id: str,
    body: ApprovalActionRequest | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    """Approve a pending response."""
    try:
        approval_uuid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid approval ID")

    # Verify tenant ownership
    stmt = (
        select(PendingApproval)
        .join(Lead, PendingApproval.lead_id == Lead.id)
        .where(PendingApproval.id == approval_uuid)
        .where(Lead.tenant_id == current_user.tenant_id)
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    try:
        reviewer_notes = body.reviewer_notes if body else None
        approval = await ApprovalQueue.approve(
            session=session,
            approval_id=approval_uuid,
            reviewer_notes=reviewer_notes,
        )
        await session.commit()
        return _serialize_approval(approval)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{approval_id}/reject")
async def reject_response(
    approval_id: str,
    body: ApprovalActionRequest | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    """Reject a pending response."""
    try:
        approval_uuid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid approval ID")

    # Verify tenant ownership
    stmt = (
        select(PendingApproval)
        .join(Lead, PendingApproval.lead_id == Lead.id)
        .where(PendingApproval.id == approval_uuid)
        .where(Lead.tenant_id == current_user.tenant_id)
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    try:
        reviewer_notes = body.reviewer_notes if body else None
        approval = await ApprovalQueue.reject(
            session=session,
            approval_id=approval_uuid,
            reviewer_notes=reviewer_notes,
        )
        await session.commit()
        return _serialize_approval(approval)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{approval_id}/edit")
async def edit_and_send_response(
    approval_id: str,
    body: ApprovalEditRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    """Edit and approve a pending response."""
    try:
        approval_uuid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid approval ID")

    # Verify tenant ownership
    stmt = (
        select(PendingApproval)
        .join(Lead, PendingApproval.lead_id == Lead.id)
        .where(PendingApproval.id == approval_uuid)
        .where(Lead.tenant_id == current_user.tenant_id)
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    edited_response = {
        "subject": body.subject,
        "body": body.body,
        "action": body.action,
    }

    try:
        approval = await ApprovalQueue.edit_and_send(
            session=session,
            approval_id=approval_uuid,
            edited_response=edited_response,
        )
        await session.commit()
        return _serialize_approval(approval)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

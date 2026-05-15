"""Telegram Client Bot - multi-tenant bot for client interactions via Telegram Bot API."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    ApprovalStatus,
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    PendingApproval,
    Tenant,
)

logger = logging.getLogger(__name__)


class TelegramClientBot:
    """Multi-tenant Telegram bot using raw Telegram Bot API via httpx."""

    def __init__(self, bot_token: str, session_factory: async_sessionmaker[AsyncSession]):
        """Initialize the Telegram client bot.

        Args:
            bot_token: The Telegram bot token for the client-facing bot.
            session_factory: Async session factory for database access.
        """
        self._token = bot_token
        self._session_factory = session_factory
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    # ---------- Core API Methods ----------

    async def send_message(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> bool:
        """Send a message via Telegram Bot API.

        Args:
            chat_id: The Telegram chat ID to send to.
            text: The message text (supports Markdown).
            reply_markup: Optional inline keyboard markup.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        url = f"{self._base_url}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if data.get("ok"):
                    return True
                logger.warning("Telegram sendMessage error: %s", data.get("description", "Unknown"))
                return False
        except httpx.HTTPError as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            return False

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """Answer a callback query from an inline button press.

        Args:
            callback_query_id: The callback query ID to answer.
            text: Optional text to show as a notification.

        Returns:
            True if answered successfully, False otherwise.
        """
        url = f"{self._base_url}/answerCallbackQuery"
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if data.get("ok"):
                    return True
                logger.warning("Telegram answerCallbackQuery error: %s", data.get("description"))
                return False
        except httpx.HTTPError as exc:
            logger.error("Failed to answer callback query: %s", exc)
            return False

    async def edit_message(
        self, chat_id: str, message_id: int, text: str, reply_markup: dict | None = None
    ) -> bool:
        """Edit an existing message.

        Args:
            chat_id: The chat ID containing the message.
            message_id: The message ID to edit.
            text: The new message text.
            reply_markup: Optional new inline keyboard markup.

        Returns:
            True if edited successfully, False otherwise.
        """
        url = f"{self._base_url}/editMessageText"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if data.get("ok"):
                    return True
                logger.warning("Telegram editMessageText error: %s", data.get("description"))
                return False
        except httpx.HTTPError as exc:
            logger.error("Failed to edit Telegram message: %s", exc)
            return False

    # ---------- Command Handlers ----------

    async def handle_status(self, chat_id: str, tenant_id: UUID) -> None:
        """Handle /status command - show campaign stats summary.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
        """
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        async with self._session_factory() as session:
            # Active campaigns count
            campaigns_result = await session.execute(
                select(func.count(Campaign.id)).where(
                    Campaign.tenant_id == tenant_id,
                    Campaign.status == CampaignStatus.active,
                )
            )
            active_campaigns = campaigns_result.scalar() or 0

            # New leads this week
            leads_result = await session.execute(
                select(func.count(Lead.id)).where(
                    Lead.tenant_id == tenant_id,
                    Lead.created_at >= week_ago,
                )
            )
            new_leads = leads_result.scalar() or 0

            # Replies this week (events of type reply for tenant's campaigns)
            replies_result = await session.execute(
                select(func.count(Event.id)).where(
                    Event.event_type == EventType.reply,
                    Event.occurred_at >= week_ago,
                    Event.message_id.in_(
                        select(Message.id).where(
                            Message.campaign_id.in_(
                                select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                            )
                        )
                    ),
                )
            )
            replies = replies_result.scalar() or 0

            # Meetings booked this week
            meetings_result = await session.execute(
                select(func.count(Lead.id)).where(
                    Lead.tenant_id == tenant_id,
                    Lead.status == LeadStatus.booked,
                    Lead.created_at >= week_ago,
                )
            )
            meetings = meetings_result.scalar() or 0

        text = (
            "*Campaign Status*\n\n"
            f"Active Campaigns: {active_campaigns}\n"
            f"New Leads (this week): {new_leads}\n"
            f"Replies (this week): {replies}\n"
            f"Meetings Booked (this week): {meetings}"
        )
        await self.send_message(chat_id, text)

    async def handle_hot(self, chat_id: str, tenant_id: UUID) -> None:
        """Handle /hot command - show top 5 hot leads.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
        """
        from agents.lead_scorer import LeadScorer

        scorer = LeadScorer(self._session_factory)
        hot_leads = await scorer.get_hot_leads(tenant_id, threshold=60)
        top_leads = hot_leads[:5]

        if not top_leads:
            await self.send_message(chat_id, "No hot leads found above threshold.")
            return

        lines = ["*Hot Leads (Top 5)*\n"]
        for i, lead in enumerate(top_leads, 1):
            name = f"{lead.first_name} {lead.last_name}"
            lines.append(f"{i}. {name} - {lead.company} (Score: {lead.score:.0f})")

        await self.send_message(chat_id, "\n".join(lines))

    async def handle_pending(self, chat_id: str, tenant_id: UUID) -> None:
        """Handle /pending command - show pending approvals with inline buttons.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
        """
        from agents.approval_queue import ApprovalQueue

        async with self._session_factory() as session:
            approvals = await ApprovalQueue.list_pending(
                session=session, tenant_id=tenant_id, limit=10
            )

        if not approvals:
            await self.send_message(chat_id, "No pending approvals.")
            return

        for approval in approvals:
            proposed = approval.proposed_response or {}
            subject = proposed.get("subject", "N/A")
            action = proposed.get("action", "N/A")
            approval_id = str(approval.id)

            text = (
                f"*Pending Approval*\n"
                f"Subject: {subject}\n"
                f"Action: {action}"
            )

            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "Approve", "callback_data": f"approve:{approval_id}"},
                        {"text": "Reject", "callback_data": f"reject:{approval_id}"},
                    ]
                ]
            }

            await self.send_message(chat_id, text, reply_markup=reply_markup)

    async def handle_approve(self, chat_id: str, tenant_id: UUID, approval_id: str) -> None:
        """Handle approval of a pending item.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
            approval_id: The approval UUID string.
        """
        from agents.approval_queue import ApprovalQueue
        import uuid

        try:
            approval_uuid = uuid.UUID(approval_id)
        except ValueError:
            await self.send_message(chat_id, "Invalid approval ID.")
            return

        try:
            async with self._session_factory() as session:
                approval = await ApprovalQueue.approve(
                    session=session,
                    approval_id=approval_uuid,
                    reviewer_notes="Approved via Telegram bot",
                )
                await session.commit()
            await self.send_message(chat_id, "Approved successfully.")
        except ValueError as exc:
            await self.send_message(chat_id, f"Error: {exc}")

    async def handle_reject(self, chat_id: str, tenant_id: UUID, approval_id: str) -> None:
        """Handle rejection of a pending item.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
            approval_id: The approval UUID string.
        """
        from agents.approval_queue import ApprovalQueue
        import uuid

        try:
            approval_uuid = uuid.UUID(approval_id)
        except ValueError:
            await self.send_message(chat_id, "Invalid approval ID.")
            return

        try:
            async with self._session_factory() as session:
                approval = await ApprovalQueue.reject(
                    session=session,
                    approval_id=approval_uuid,
                    reviewer_notes="Rejected via Telegram bot",
                )
                await session.commit()
            await self.send_message(chat_id, "Rejected successfully.")
        except ValueError as exc:
            await self.send_message(chat_id, f"Error: {exc}")

    async def handle_pause(self, chat_id: str, tenant_id: UUID, campaign_name: str) -> None:
        """Handle /pause command - pause a campaign by name.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
            campaign_name: The campaign name to pause.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Campaign).where(
                    Campaign.tenant_id == tenant_id,
                    Campaign.name == campaign_name,
                )
            )
            campaign = result.scalar_one_or_none()

            if campaign is None:
                await self.send_message(chat_id, f"Campaign '{campaign_name}' not found.")
                return

            campaign.status = CampaignStatus.paused
            await session.commit()

        await self.send_message(chat_id, f"Campaign '{campaign_name}' has been paused.")

    async def handle_resume(self, chat_id: str, tenant_id: UUID, campaign_name: str) -> None:
        """Handle /resume command - resume a campaign by name.

        Args:
            chat_id: The chat ID to respond to.
            tenant_id: The tenant UUID for data isolation.
            campaign_name: The campaign name to resume.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Campaign).where(
                    Campaign.tenant_id == tenant_id,
                    Campaign.name == campaign_name,
                )
            )
            campaign = result.scalar_one_or_none()

            if campaign is None:
                await self.send_message(chat_id, f"Campaign '{campaign_name}' not found.")
                return

            campaign.status = CampaignStatus.active
            await session.commit()

        await self.send_message(chat_id, f"Campaign '{campaign_name}' has been resumed.")

    # ---------- Real-Time Notification Methods ----------

    async def notify_positive_reply(self, tenant_id: UUID, lead_data: dict) -> bool:
        """Send notification about a positive reply from a lead.

        Args:
            tenant_id: The tenant UUID.
            lead_data: Dict with lead info (name, company, email).

        Returns:
            True if notification was sent, False otherwise.
        """
        chat_id = await self._get_chat_id_for_tenant(tenant_id)
        if not chat_id:
            return False

        name = lead_data.get("name", "Unknown")
        company = lead_data.get("company", "Unknown")
        email = lead_data.get("email", "Unknown")

        text = (
            "*Positive Reply Received!*\n\n"
            f"Lead: {name}\n"
            f"Company: {company}\n"
            f"Email: {email}"
        )
        return await self.send_message(chat_id, text)

    async def notify_meeting_booked(self, tenant_id: UUID, lead_data: dict) -> bool:
        """Send notification about a meeting being booked.

        Args:
            tenant_id: The tenant UUID.
            lead_data: Dict with lead info (name, company, email).

        Returns:
            True if notification was sent, False otherwise.
        """
        chat_id = await self._get_chat_id_for_tenant(tenant_id)
        if not chat_id:
            return False

        name = lead_data.get("name", "Unknown")
        company = lead_data.get("company", "Unknown")

        text = (
            "*Meeting Booked!*\n\n"
            f"Lead: {name}\n"
            f"Company: {company}"
        )
        return await self.send_message(chat_id, text)

    async def notify_domain_paused(self, tenant_id: UUID, domain: str, reason: str) -> bool:
        """Send notification about a domain being paused.

        Args:
            tenant_id: The tenant UUID.
            domain: The domain that was paused.
            reason: The reason for pausing.

        Returns:
            True if notification was sent, False otherwise.
        """
        chat_id = await self._get_chat_id_for_tenant(tenant_id)
        if not chat_id:
            return False

        text = (
            "*Domain Paused*\n\n"
            f"Domain: {domain}\n"
            f"Reason: {reason}"
        )
        return await self.send_message(chat_id, text)

    async def notify_weekly_digest(self, tenant_id: UUID, stats: dict) -> bool:
        """Send weekly digest stats to tenant.

        Args:
            tenant_id: The tenant UUID.
            stats: Dict with weekly stats (qualified_leads, meetings_booked, etc).

        Returns:
            True if notification was sent, False otherwise.
        """
        chat_id = await self._get_chat_id_for_tenant(tenant_id)
        if not chat_id:
            return False

        qualified = stats.get("qualified_leads", 0)
        meetings = stats.get("meetings_booked", 0)
        pipeline = stats.get("pipeline_value", 0)
        top_campaign = stats.get("top_campaign", "N/A")
        open_rate = stats.get("open_rate", 0.0)
        reply_rate = stats.get("reply_rate", 0.0)

        text = (
            "*Weekly Digest*\n\n"
            f"Qualified Leads: {qualified}\n"
            f"Meetings Booked: {meetings}\n"
            f"Pipeline Value: ${pipeline:,}\n"
            f"Top Campaign: {top_campaign}\n"
            f"Open Rate: {open_rate}%\n"
            f"Reply Rate: {reply_rate}%"
        )
        return await self.send_message(chat_id, text)

    # ---------- Helpers ----------

    async def _get_chat_id_for_tenant(self, tenant_id: UUID) -> str | None:
        """Look up the telegram_client_chat_id from tenant settings.

        Args:
            tenant_id: The tenant UUID.

        Returns:
            The chat ID string, or None if not configured.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            tenant = result.scalar_one_or_none()
            if tenant is None:
                return None

            settings = tenant.settings or {}
            return settings.get("telegram_client_chat_id")

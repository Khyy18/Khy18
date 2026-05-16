"""Weekly report generation and delivery logic."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    Campaign,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    ChannelType,
    Tenant,
)

logger = logging.getLogger(__name__)


def format_telegram_report(report_data: dict[str, Any]) -> str:
    """Format the weekly report as a Markdown Telegram message.

    Uses emoji indicators for positive/negative deltas.
    """
    period = report_data.get("period", "")

    def _fmt_metric(label: str, metric: dict[str, Any]) -> str:
        current = metric.get("current", 0)
        previous = metric.get("previous", 0)
        delta = metric.get("delta_percent", 0)
        if isinstance(current, float):
            current_str = f"{current:.1f}%"
            previous_str = f"{previous:.1f}%"
        else:
            current_str = str(current)
            previous_str = str(previous)
        arrow = "\u2b06\ufe0f" if delta >= 0 else "\u2b07\ufe0f"
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        return f"*{label}:* {current_str} (prev: {previous_str}, {arrow} {delta_str}%)"

    lines = [
        "*Weekly Performance Report*",
        f"Period: {period}",
        "",
    ]

    metrics_map = [
        ("Leads Contacted", "leads_contacted"),
        ("Emails Sent", "emails_sent"),
        ("Open Rate", "open_rate"),
        ("Reply Rate", "reply_rate"),
        ("Meetings Booked", "meetings_booked"),
        ("Hot Leads", "hot_leads"),
    ]

    for label, key in metrics_map:
        metric = report_data.get("metrics", {}).get(key, {})
        lines.append(_fmt_metric(label, metric))

    return "\n".join(lines)


class WeeklyReportGenerator:
    """Generates weekly performance reports for tenants."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None):
        self.session_factory = session_factory

    async def generate_report(
        self, tenant_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        """Compute metrics for this week and previous week with delta percentages.

        Returns dict with keys for each metric, each having:
        current, previous, delta_percent.
        """
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        period_str = f"{week_ago.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"

        # -- Leads contacted (status != 'new', created this week) --
        leads_contacted_current = await self._count_leads_contacted(
            tenant_id, week_ago, now, session
        )
        leads_contacted_previous = await self._count_leads_contacted(
            tenant_id, two_weeks_ago, week_ago, session
        )

        # -- Emails sent (channel=email, sent_at this week) --
        emails_sent_current = await self._count_emails_sent(
            tenant_id, week_ago, now, session
        )
        emails_sent_previous = await self._count_emails_sent(
            tenant_id, two_weeks_ago, week_ago, session
        )

        # -- Opens this week --
        opens_current = await self._count_events(
            tenant_id, EventType.open, week_ago, now, session
        )
        opens_previous = await self._count_events(
            tenant_id, EventType.open, two_weeks_ago, week_ago, session
        )

        # -- Replies this week --
        replies_current = await self._count_events(
            tenant_id, EventType.reply, week_ago, now, session
        )
        replies_previous = await self._count_events(
            tenant_id, EventType.reply, two_weeks_ago, week_ago, session
        )

        # -- Rates --
        open_rate_current = (
            (opens_current / emails_sent_current * 100)
            if emails_sent_current > 0
            else 0.0
        )
        open_rate_previous = (
            (opens_previous / emails_sent_previous * 100)
            if emails_sent_previous > 0
            else 0.0
        )

        reply_rate_current = (
            (replies_current / emails_sent_current * 100)
            if emails_sent_current > 0
            else 0.0
        )
        reply_rate_previous = (
            (replies_previous / emails_sent_previous * 100)
            if emails_sent_previous > 0
            else 0.0
        )

        # -- Meetings booked (leads with status='booked' created this week) --
        meetings_current = await self._count_leads_by_status(
            tenant_id, LeadStatus.booked, week_ago, now, session
        )
        meetings_previous = await self._count_leads_by_status(
            tenant_id, LeadStatus.booked, two_weeks_ago, week_ago, session
        )

        # -- Hot leads (score >= 70, created this week) --
        hot_leads_current = await self._count_hot_leads(
            tenant_id, week_ago, now, session
        )
        hot_leads_previous = await self._count_hot_leads(
            tenant_id, two_weeks_ago, week_ago, session
        )

        metrics = {
            "leads_contacted": self._make_metric(
                leads_contacted_current, leads_contacted_previous
            ),
            "emails_sent": self._make_metric(
                emails_sent_current, emails_sent_previous
            ),
            "open_rate": self._make_metric(
                round(open_rate_current, 1), round(open_rate_previous, 1)
            ),
            "reply_rate": self._make_metric(
                round(reply_rate_current, 1), round(reply_rate_previous, 1)
            ),
            "meetings_booked": self._make_metric(
                meetings_current, meetings_previous
            ),
            "hot_leads": self._make_metric(
                hot_leads_current, hot_leads_previous
            ),
        }

        return {
            "tenant_id": str(tenant_id),
            "period": period_str,
            "generated_at": now.isoformat(),
            "metrics": metrics,
        }

    async def deliver_report(
        self, tenant_id: UUID, report_data: dict[str, Any], session: AsyncSession
    ) -> dict[str, Any]:
        """Deliver the report via configured channels (email/telegram/both).

        Reads tenant.settings['report_preferences'] for delivery configuration.
        """
        from integrations.notifications import (
            send_email_digest,
            send_telegram_notification,
        )

        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            return {"delivered_via": [], "success": False}

        settings_data = tenant.settings or {}
        preferences = settings_data.get("report_preferences", {})

        if not preferences:
            return {"delivered_via": [], "success": False}

        delivery_method = preferences.get("delivery_method", "email")
        email_address = preferences.get("email_address", "")
        telegram_chat_id = preferences.get("telegram_chat_id", "")

        delivered_via: list[str] = []
        any_success = False

        # Email delivery
        if delivery_method in ("email", "both") and email_address:
            html_body = self._render_html_report(report_data)
            success = await send_email_digest(
                to_email=email_address,
                subject="Weekly Performance Report",
                html_body=html_body,
            )
            if success:
                delivered_via.append("email")
                any_success = True

        # Telegram delivery
        if delivery_method in ("telegram", "both") and telegram_chat_id:
            import os

            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            text = format_telegram_report(report_data)
            success = await send_telegram_notification(
                bot_token=bot_token,
                chat_id=telegram_chat_id,
                text=text,
            )
            if success:
                delivered_via.append("telegram")
                any_success = True

        return {"delivered_via": delivered_via, "success": any_success}

    def _render_html_report(self, report_data: dict[str, Any]) -> str:
        """Render the HTML email template for the report."""
        import os
        from jinja2 import Environment, FileSystemLoader

        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "dashboard",
            "templates",
            "reports",
        )
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("weekly_report.html")
        return template.render(report=report_data)

    @staticmethod
    def _make_metric(current: Any, previous: Any) -> dict[str, Any]:
        """Create a metric dict with current, previous, and delta_percent."""
        if isinstance(current, float) or isinstance(previous, float):
            curr_val = float(current)
            prev_val = float(previous)
        else:
            curr_val = current
            prev_val = previous

        if prev_val > 0:
            delta_percent = round(((curr_val - prev_val) / prev_val) * 100, 1)
        elif prev_val == 0 and curr_val > 0:
            delta_percent = 100.0
        else:
            delta_percent = 0.0

        return {
            "current": current,
            "previous": previous,
            "delta_percent": delta_percent,
        }

    async def _count_leads_contacted(
        self,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
        session: AsyncSession,
    ) -> int:
        result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.status != LeadStatus.new,
                Lead.created_at >= start,
                Lead.created_at < end,
            )
        )
        return result.scalar() or 0

    async def _count_emails_sent(
        self,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
        session: AsyncSession,
    ) -> int:
        result = await session.execute(
            select(func.count(Message.id)).where(
                Message.channel == ChannelType.email,
                Message.sent_at >= start,
                Message.sent_at < end,
                Message.campaign_id.in_(
                    select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                ),
            )
        )
        return result.scalar() or 0

    async def _count_events(
        self,
        tenant_id: UUID,
        event_type: EventType,
        start: datetime,
        end: datetime,
        session: AsyncSession,
    ) -> int:
        result = await session.execute(
            select(func.count(Event.id)).where(
                Event.event_type == event_type,
                Event.occurred_at >= start,
                Event.occurred_at < end,
                Event.message_id.in_(
                    select(Message.id).where(
                        Message.campaign_id.in_(
                            select(Campaign.id).where(
                                Campaign.tenant_id == tenant_id
                            )
                        )
                    )
                ),
            )
        )
        return result.scalar() or 0

    async def _count_leads_by_status(
        self,
        tenant_id: UUID,
        lead_status: LeadStatus,
        start: datetime,
        end: datetime,
        session: AsyncSession,
    ) -> int:
        result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.status == lead_status,
                Lead.created_at >= start,
                Lead.created_at < end,
            )
        )
        return result.scalar() or 0

    async def _count_hot_leads(
        self,
        tenant_id: UUID,
        start: datetime,
        end: datetime,
        session: AsyncSession,
    ) -> int:
        result = await session.execute(
            select(func.count(Lead.id)).where(
                Lead.tenant_id == tenant_id,
                Lead.score >= 70,
                Lead.created_at >= start,
                Lead.created_at < end,
            )
        )
        return result.scalar() or 0

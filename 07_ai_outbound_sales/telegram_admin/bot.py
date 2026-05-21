"""Telegram Admin Bot for AI Outbound Agency.

Provides admin commands to monitor and control campaigns via Telegram.
Uses aiogram 3 framework.

Commands:
    /start   - Welcome message with available commands
    /stats   - Today's metrics (leads created, emails sent, calls made)
    /campaigns - List active campaigns with status emoji
    /calls   - 5 most recent calls with duration and outcome
    /alerts  - Current health issues (or "All systems healthy")
    /pause   - Pause all active campaigns
    /resume  - Resume paused campaigns

Usage:
    TELEGRAM_ADMIN_BOT_TOKEN=your_token DATABASE_URL=... python telegram_admin/bot.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    Call,
    CallOutcome,
    CallStatus,
    Campaign,
    CampaignStatus,
    Lead,
    Message,
    MessageStatus,
)
from telegram_admin.config import ADMIN_CHAT_IDS, DATABASE_URL, TELEGRAM_BOT_TOKEN

engine = create_async_engine(DATABASE_URL, echo=False)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

router = Router()


STATUS_EMOJI = {
    CampaignStatus.active: "🟢",
    CampaignStatus.paused: "🟡",
    CampaignStatus.draft: "⚪",
    CampaignStatus.completed: "✅",
}

OUTCOME_EMOJI = {
    CallOutcome.qualified: "✅",
    CallOutcome.not_interested: "❌",
    CallOutcome.voicemail: "📞",
    CallOutcome.no_answer: "📵",
    CallOutcome.error: "⚠️",
    CallOutcome.busy: "🔴",
}


async def _check_access(message: types.Message) -> bool:
    """Check if the user is in the ADMIN_CHAT_IDS allowlist.

    Returns True if access is denied (caller should return early).
    """
    if ADMIN_CHAT_IDS and message.from_user.id not in ADMIN_CHAT_IDS:
        await message.answer("Access denied")
        return True
    return False


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Handle /start command - display welcome and available commands."""
    if await _check_access(message):
        return
    text = (
        "🤖 *AI Outbound Agency Admin Bot*\n\n"
        "Available commands:\n"
        "/stats - Today's metrics\n"
        "/campaigns - List active campaigns\n"
        "/calls - Recent calls\n"
        "/alerts - Health status\n"
        "/pause - Pause all active campaigns\n"
        "/resume - Resume paused campaigns"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    """Handle /stats command - show today's metrics."""
    if await _check_access(message):
        return
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    async with session_factory() as session:
        # Leads created today
        leads_result = await session.execute(
            select(func.count(Lead.id)).where(Lead.created_at >= today_start)
        )
        leads_count = leads_result.scalar() or 0

        # Emails sent today
        emails_result = await session.execute(
            select(func.count(Message.id)).where(
                Message.sent_at >= today_start,
                Message.status == MessageStatus.sent,
            )
        )
        emails_count = emails_result.scalar() or 0

        # Calls made today
        calls_result = await session.execute(
            select(func.count(Call.id)).where(Call.started_at >= today_start)
        )
        calls_count = calls_result.scalar() or 0

        # Meetings booked (calls with qualified outcome today)
        meetings_result = await session.execute(
            select(func.count(Call.id)).where(
                Call.started_at >= today_start,
                Call.outcome == CallOutcome.qualified,
            )
        )
        meetings_count = meetings_result.scalar() or 0

    text = (
        "📊 *Today's Metrics*\n\n"
        f"👥 Leads created: {leads_count}\n"
        f"📧 Emails sent: {emails_count}\n"
        f"📞 Calls made: {calls_count}\n"
        f"📅 Meetings booked: {meetings_count}"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("campaigns"))
async def cmd_campaigns(message: types.Message) -> None:
    """Handle /campaigns command - list active campaigns."""
    if await _check_access(message):
        return
    async with session_factory() as session:
        result = await session.execute(
            select(Campaign).where(
                Campaign.status.in_([CampaignStatus.active, CampaignStatus.paused])
            )
        )
        campaigns = result.scalars().all()

    if not campaigns:
        await message.answer("No active or paused campaigns found.")
        return

    lines = ["📋 *Active Campaigns*\n"]
    for c in campaigns:
        emoji = STATUS_EMOJI.get(c.status, "❓")
        lines.append(f"{emoji} {c.name} ({c.status.value})")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("calls"))
async def cmd_calls(message: types.Message) -> None:
    """Handle /calls command - show 5 most recent calls."""
    if await _check_access(message):
        return
    async with session_factory() as session:
        result = await session.execute(
            select(Call).order_by(Call.started_at.desc()).limit(5)
        )
        calls = result.scalars().all()

    if not calls:
        await message.answer("No calls found.")
        return

    lines = ["📞 *Recent Calls*\n"]
    for call in calls:
        duration = f"{call.duration_seconds}s" if call.duration_seconds else "N/A"
        outcome_emoji = OUTCOME_EMOJI.get(call.outcome, "❓") if call.outcome else "⏳"
        outcome_text = call.outcome.value if call.outcome else "in progress"
        lines.append(f"{outcome_emoji} {duration} - {outcome_text}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("alerts"))
async def cmd_alerts(message: types.Message) -> None:
    """Handle /alerts command - check system health."""
    if await _check_access(message):
        return
    # Simple health checks
    issues = []

    try:
        async with session_factory() as session:
            await session.execute(select(func.count(Lead.id)))
    except Exception as exc:
        issues.append(f"Database: {str(exc)[:50]}")

    if not issues:
        await message.answer("✅ All systems healthy!")
    else:
        text = "⚠️ *Health Issues*\n\n" + "\n".join(f"• {i}" for i in issues)
        await message.answer(text, parse_mode="Markdown")


@router.message(Command("pause"))
async def cmd_pause(message: types.Message) -> None:
    """Handle /pause command - pause all active campaigns."""
    if await _check_access(message):
        return
    async with session_factory() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.active)
        )
        campaigns = result.scalars().all()

        count = 0
        for c in campaigns:
            c.status = CampaignStatus.paused
            count += 1

        await session.commit()

    await message.answer(f"⏸️ Paused {count} campaign(s).")


@router.message(Command("resume"))
async def cmd_resume(message: types.Message) -> None:
    """Handle /resume command - resume all paused campaigns."""
    if await _check_access(message):
        return
    async with session_factory() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.paused)
        )
        campaigns = result.scalars().all()

        count = 0
        for c in campaigns:
            c.status = CampaignStatus.active
            count += 1

        await session.commit()

    await message.answer(f"▶️ Resumed {count} campaign(s).")


async def main() -> None:
    """Start the Telegram admin bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_ADMIN_BOT_TOKEN environment variable is not set")
        sys.exit(1)

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("Starting Telegram Admin Bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

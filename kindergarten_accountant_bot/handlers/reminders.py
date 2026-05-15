"""Handlers for deadline reminders management."""

import logging
from datetime import date, datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden
from telegram.ext import CallbackQueryHandler, ContextTypes

from kindergarten_accountant_bot.data.deadlines import DEADLINES
from kindergarten_accountant_bot.models.reminder import (
    get_all_reminders_status,
    get_chats_with_reminders,
    get_enabled_reminders,
    get_next_deadline_date,
    set_reminder_status,
)
from kindergarten_accountant_bot.utils.formatting import _card
from kindergarten_accountant_bot.utils.keyboards import back_to_menu_button


async def reminders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reminders sub-menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Мои напоминания", callback_data="rem_list")],
        [InlineKeyboardButton("Ближайшие сроки", callback_data="rem_upcoming")],
        [InlineKeyboardButton("\u25c0 Главное меню", callback_data="back_to_menu")],
    ]
    await query.edit_message_text(
        "<b>Напоминания</b>\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def reminders_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all deadlines with toggle status."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    statuses = await get_all_reminders_status(chat_id)

    keyboard = []
    for deadline in DEADLINES:
        name = deadline["name"]
        enabled = statuses.get(name, False)
        icon = "\U0001f7e2" if enabled else "\u26aa"
        keyboard.append(
            [InlineKeyboardButton(
                f"{icon} {name}",
                callback_data=f"rem_toggle_{name}",
            )]
        )
    keyboard.append(
        [InlineKeyboardButton("\u25c0 Назад", callback_data="menu_reminders")]
    )
    await query.edit_message_text(
        "<b>Мои напоминания</b>\n\nНажмите для включения/отключения:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def toggle_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle reminder enabled/disabled status."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    reminder_name = query.data.replace("rem_toggle_", "")

    statuses = await get_all_reminders_status(chat_id)
    current_status = statuses.get(reminder_name, False)
    await set_reminder_status(chat_id, reminder_name, not current_status)

    # Refresh the list
    statuses = await get_all_reminders_status(chat_id)
    keyboard = []
    for deadline in DEADLINES:
        name = deadline["name"]
        enabled = statuses.get(name, False)
        icon = "\U0001f7e2" if enabled else "\u26aa"
        keyboard.append(
            [InlineKeyboardButton(
                f"{icon} {name}",
                callback_data=f"rem_toggle_{name}",
            )]
        )
    keyboard.append(
        [InlineKeyboardButton("\u25c0 Назад", callback_data="menu_reminders")]
    )
    await query.edit_message_text(
        "<b>Мои напоминания</b>\n\nНажмите для включения/отключения:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def upcoming_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show next 5 upcoming deadlines for enabled reminders."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    enabled = await get_enabled_reminders(chat_id)

    if not enabled:
        await query.edit_message_text(
            "Нет включённых напоминаний. Включите в разделе 'Мои напоминания'.",
            reply_markup=back_to_menu_button(),
        )
        return

    today = date.today()
    upcoming = []
    for deadline in DEADLINES:
        if deadline["name"] in enabled:
            next_date = get_next_deadline_date(deadline, today)
            days_left = (next_date - today).days
            upcoming.append((deadline["name"], next_date, days_left))

    upcoming.sort(key=lambda x: x[1])
    upcoming = upcoming[:5]

    body_lines = []
    for name, d, days_left in upcoming:
        if days_left <= 3:
            color = "\U0001f534"
        elif days_left <= 7:
            color = "\U0001f7e1"
        else:
            color = "\U0001f7e2"
        date_str = d.strftime("%d.%m.%Y")
        body_lines.append(f"{color} {name} \u2014 {date_str} (через {days_left} дн.)")

    card = _card("Ближайшие дедлайны", "\u23f0", body_lines)
    await query.edit_message_text(
        card,
        reply_markup=back_to_menu_button(),
        parse_mode="HTML",
    )


async def daily_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Daily job: check deadlines and send reminders."""
    today = date.today()
    chat_ids = await get_chats_with_reminders()

    for chat_id in chat_ids:
        enabled = await get_enabled_reminders(chat_id)
        alerts = []
        for deadline in DEADLINES:
            if deadline["name"] not in enabled:
                continue
            next_date = get_next_deadline_date(deadline, today)
            days_left = (next_date - today).days
            if days_left == 0:
                alerts.append(f"\U0001f534 СЕГОДНЯ: {deadline['name']} - {deadline['description']}")
            elif days_left == 3:
                alerts.append(f"\U0001f7e1 Через 3 дня: {deadline['name']} - {deadline['description']}")

        if alerts:
            body_lines = alerts
            card = _card("Напоминание о дедлайнах", "\U0001f514", body_lines)
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=card,
                    parse_mode="HTML",
                )
            except Forbidden:
                logging.warning("User %s blocked the bot", chat_id)
            except Exception as e:
                logging.warning("Failed to send reminder to %s: %s", chat_id, e)


def setup_reminder_jobs(application):
    """Set up daily reminder job at 09:00 Moscow time."""
    moscow_tz = timezone(timedelta(hours=3))
    job_time = datetime(2000, 1, 1, 9, 0, 0, tzinfo=moscow_tz).timetz()
    application.job_queue.run_daily(
        daily_reminder_job,
        time=job_time,
        name="daily_reminders",
    )


reminders_handler = [
    CallbackQueryHandler(reminders_menu, pattern="^menu_reminders$"),
    CallbackQueryHandler(reminders_list, pattern="^rem_list$"),
    CallbackQueryHandler(toggle_reminder, pattern="^rem_toggle_.+$"),
    CallbackQueryHandler(upcoming_deadlines, pattern="^rem_upcoming$"),
]

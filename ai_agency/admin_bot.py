"""Админский Telegram-бот AI-агентства (python-telegram-bot v20+)."""

import functools
import logging
import sys

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

import config
import database
import billing
import analytics
from utils import _card, format_number, status_indicator

logger = logging.getLogger(__name__)

# Состояния для пополнения баланса
TOPUP_CLIENT_ID, TOPUP_AMOUNT = range(2)


def admin_only(func):
    """Декоратор для проверки доступа администратора."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != config.ADMIN_TELEGRAM_ID:
            await update.message.reply_text(
                "\U0001f6ab Доступ запрещён.",
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def admin_only_callback(func):
    """Декоратор для проверки доступа в callback."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != config.ADMIN_TELEGRAM_ID:
            query = update.callback_query
            await query.answer("\U0001f6ab Доступ запрещён.", show_alert=True)
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


# --- Главное меню ---

@admin_only
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Главное меню администратора."""
    body = [
        "Панель управления AI-агентством.",
        "",
        "Выберите действие:",
    ]
    text = _card("Админ-панель", "\U0001f6e0\ufe0f", body)

    keyboard = [
        [InlineKeyboardButton("\U0001f4ca Статистика", callback_data="stats")],
        [InlineKeyboardButton("\U0001f4c8 Аналитика", callback_data="analytics")],
        [InlineKeyboardButton("\U0001f4cb Последние заказы", callback_data="recent_orders")],
        [InlineKeyboardButton("\U0001f465 Клиенты", callback_data="clients")],
        [InlineKeyboardButton("\U0001f4b3 Пополнить баланс", callback_data="topup")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )
    return SELECT_ACTION


# --- Состояния ---
SELECT_ACTION = 0


@admin_only_callback
async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора действия в меню."""
    query = update.callback_query
    await query.answer()

    action = query.data

    if action == "stats":
        return await show_stats(update, context)
    elif action == "analytics":
        return await show_analytics(update, context)
    elif action == "recent_orders":
        return await show_recent_orders(update, context)
    elif action == "clients":
        return await show_clients(update, context)
    elif action == "topup":
        await query.edit_message_text(
            "\U0001f4b3 Введите Telegram ID клиента для пополнения:",
            parse_mode=ParseMode.HTML,
        )
        return TOPUP_CLIENT_ID

    return ConversationHandler.END


# --- Статистика ---

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать статистику за периоды."""
    query = update.callback_query

    day_orders, day_revenue = await database.get_stats_for_period(1)
    week_orders, week_revenue = await database.get_stats_for_period(7)
    month_orders, month_revenue = await database.get_stats_for_period(30)

    body = [
        "<b>За сутки:</b>",
        f"  Заказов: {day_orders}",
        f"  Выручка: {format_number(day_revenue)} \u20bd",
        "",
        "<b>За неделю:</b>",
        f"  Заказов: {week_orders}",
        f"  Выручка: {format_number(week_revenue)} \u20bd",
        "",
        "<b>За месяц:</b>",
        f"  Заказов: {month_orders}",
        f"  Выручка: {format_number(month_revenue)} \u20bd",
    ]
    text = _card("Статистика", "\U0001f4ca", body)

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Аналитика (дашборд) ---

async def show_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать аналитический дашборд."""
    query = update.callback_query

    data = await analytics.get_dashboard_data()
    text = analytics.format_dashboard(data)

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Последние заказы ---

async def show_recent_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать последние заказы."""
    query = update.callback_query
    orders = await database.get_recent_orders(limit=10)

    if not orders:
        body = ["Заказов пока нет."]
    else:
        body = []
        for order in orders:
            body.append(
                f"{status_indicator(order['status'])} "
                f"#{order['id']} | {order['service_type']} | "
                f"Клиент: {order['client_id']} | "
                f"{format_number(order['price'])} \u20bd"
            )

    text = _card("Последние заказы", "\U0001f4cb", body)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Клиенты ---

async def show_clients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список клиентов."""
    query = update.callback_query
    clients = await database.get_all_clients()

    if not clients:
        body = ["Клиентов пока нет."]
    else:
        body = []
        for client in clients[:20]:  # Максимум 20
            name = client.get("first_name") or client.get("username") or "N/A"
            body.append(
                f"\U0001f464 {name} (ID: {client['telegram_id']}) | "
                f"Баланс: {format_number(client['balance'])} \u20bd | "
                f"Потрачено: {format_number(client['total_spent'])} \u20bd"
            )

    text = _card("Клиенты", "\U0001f465", body)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Пополнение баланса ---

async def topup_client_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение ID клиента для пополнения."""
    try:
        client_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "\u274c Введите корректный числовой Telegram ID.",
            parse_mode=ParseMode.HTML,
        )
        return TOPUP_CLIENT_ID

    context.user_data["topup_client_id"] = client_id
    await update.message.reply_text(
        f"\U0001f4b3 Введите сумму пополнения для клиента {client_id} (в рублях):",
        parse_mode=ParseMode.HTML,
    )
    return TOPUP_AMOUNT


async def topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение суммы и выполнение пополнения."""
    try:
        amount = float(update.message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")
    except ValueError:
        await update.message.reply_text(
            "\u274c Введите корректную положительную сумму.",
            parse_mode=ParseMode.HTML,
        )
        return TOPUP_AMOUNT

    client_id = context.user_data["topup_client_id"]

    # Проверяем что клиент существует
    await database.get_or_create_client(telegram_id=client_id)

    new_balance = await billing.top_up_balance(client_id, amount, method="admin")

    body = [
        f"<b>Клиент:</b> {client_id}",
        f"<b>Сумма:</b> +{format_number(amount)} \u20bd",
        f"<b>Новый баланс:</b> {format_number(new_balance)} \u20bd",
    ]
    text = _card("Баланс пополнен", "\u2705", body)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Отмена ---

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена операции."""
    await update.message.reply_text(
        "\u274c Операция отменена. /start для меню.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


def create_admin_application() -> Application:
    """Создать и настроить приложение админ-бота."""
    application = Application.builder().token(config.TELEGRAM_ADMIN_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", admin_start)],
        states={
            SELECT_ACTION: [
                CallbackQueryHandler(handle_action),
            ],
            TOPUP_CLIENT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_client_id),
            ],
            TOPUP_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, topup_amount),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    return application


def main() -> None:
    """Запуск админского бота."""
    from config import validate_config

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    errors = validate_config()
    if errors:
        for err in errors:
            logger.error(err)
        sys.exit(1)

    import asyncio
    asyncio.run(database.init_db())

    app = create_admin_application()
    app.run_polling()


if __name__ == "__main__":
    main()

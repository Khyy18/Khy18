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

# Интеграция CRM и мониторинга (graceful)
try:
    import crm
except ImportError:
    crm = None

try:
    import monitoring
except ImportError:
    monitoring = None

logger = logging.getLogger(__name__)

# Состояния для пополнения баланса и CRM
TOPUP_CLIENT_ID, TOPUP_AMOUNT, CRM_CLIENT_ID = range(3)


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
        [InlineKeyboardButton("\U0001f4c7 CRM", callback_data="crm")],
        [InlineKeyboardButton("\U0001f6e1\ufe0f Мониторинг", callback_data="monitoring")],
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
    elif action == "crm":
        return await show_crm(update, context)
    elif action == "crm_timeline":
        await query.edit_message_text(
            "\U0001f4c7 Введите Telegram ID клиента для просмотра таймлайна:",
            parse_mode=ParseMode.HTML,
        )
        return CRM_CLIENT_ID
    elif action == "monitoring":
        return await show_monitoring(update, context)
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


# --- CRM ---

async def show_crm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать CRM: статистику сегментов."""
    query = update.callback_query

    if crm is None:
        await query.edit_message_text(
            "\u274c Модуль CRM недоступен.", parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    segments = await crm.update_segments()
    body = [
        "<b>Сегменты клиентов:</b>",
        "",
        f"\U0001f195 Новые: {segments.get('new', 0)}",
        f"\U0001f525 Активные: {segments.get('active', 0)}",
        f"\U0001f451 VIP: {segments.get('vip', 0)}",
        f"\U0001f634 Спящие: {segments.get('sleeping', 0)}",
    ]
    text = _card("CRM", "\U0001f4c7", body)

    keyboard = [
        [InlineKeyboardButton("\U0001f4cb Timeline клиента", callback_data="crm_timeline")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )
    return SELECT_ACTION


async def crm_client_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение ID клиента для CRM таймлайна."""
    try:
        client_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "\u274c Введите корректный числовой Telegram ID.",
            parse_mode=ParseMode.HTML,
        )
        return CRM_CLIENT_ID

    if crm is None:
        await update.message.reply_text(
            "\u274c Модуль CRM недоступен.", parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    segment = await crm.get_client_segment(client_id)
    timeline = await crm.get_client_timeline(client_id)

    body = [
        f"<b>Клиент:</b> {client_id}",
        f"<b>Сегмент:</b> {segment}",
        "",
        "<b>Последние события:</b>",
    ]
    for event in timeline[:10]:
        event_type = event.get("type", "")
        amount = event.get("amount", 0)
        ts = event.get("timestamp", "")[:16]
        if event_type == "order":
            body.append(f"  \U0001f4e6 Заказ #{event['id']} | {event.get('status', '')} | {amount} \u20bd | {ts}")
        elif event_type == "payment":
            body.append(f"  \U0001f4b3 Платёж #{event['id']} | {event.get('method', '')} | {amount} \u20bd | {ts}")

    if not timeline:
        body.append("  Нет событий.")

    text = _card("Timeline", "\U0001f4c7", body)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Мониторинг ---

async def show_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать мониторинг: health check и метрики."""
    query = update.callback_query

    if monitoring is None:
        await query.edit_message_text(
            "\u274c Модуль мониторинга недоступен.", parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    health = await monitoring.health_check()
    metrics = monitoring.metrics.get_metrics()

    status_emoji = "\u2705" if health["status"] == "healthy" else "\u26a0\ufe0f"
    body = [
        f"<b>Статус:</b> {status_emoji} {health['status']}",
        "",
        "<b>Компоненты:</b>",
    ]
    for name, check in health.get("checks", {}).items():
        indicator = "\u2705" if check["status"] == "ok" else "\u274c"
        body.append(f"  {indicator} {name}: {check['status']}")

    body.extend([
        "",
        "<b>Метрики:</b>",
        f"  Заказов в очереди: {metrics.get('orders_in_queue', 0)}",
        f"  Среднее время обработки: {metrics.get('avg_processing_time', 0)} сек",
        f"  Ошибок (rate): {metrics.get('error_rate', 0)}%",
        f"  Uptime: {int(metrics.get('uptime_seconds', 0) / 3600)} ч",
        f"  Всего обработано: {metrics.get('total_orders_processed', 0)}",
        f"  Всего ошибок: {metrics.get('total_errors', 0)}",
    ])

    text = _card("Мониторинг", "\U0001f6e1\ufe0f", body)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
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
            CRM_CLIENT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, crm_client_id),
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

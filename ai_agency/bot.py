"""Клиентский Telegram-бот AI-агентства (python-telegram-bot v20+)."""

import html
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
import pipeline
from models import ServiceType, OrderStatus
from services import SERVICES, get_service
from utils import _card, format_number, progress_bar, status_indicator

logger = logging.getLogger(__name__)

# Состояния ConversationHandler
SELECT_SERVICE, ENTER_TEXT, CONFIRM_ORDER = range(3)


# --- Команда /start ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветствие и показ услуг."""
    user = update.effective_user
    await database.get_or_create_client(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    # Карточка приветствия
    body = [
        f"Привет, <b>{user.first_name or 'друг'}</b>!",
        "",
        "Я AI-агентство для работы с текстами.",
        "Выбери услугу из списка ниже:",
    ]
    welcome = _card("AI-Агентство", "\U0001f916", body)

    # Инлайн-клавиатура с услугами
    keyboard = []
    for stype, sdef in SERVICES.items():
        keyboard.append([
            InlineKeyboardButton(
                f"{sdef.name} - {format_number(sdef.price)} \u20bd",
                callback_data=f"service:{stype.value}",
            )
        ])
    keyboard.append([
        InlineKeyboardButton("\U0001f4b0 Мой баланс", callback_data="balance"),
    ])
    keyboard.append([
        InlineKeyboardButton("\U0001f4cb Мои заказы", callback_data="my_orders"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )
    return SELECT_SERVICE


# --- Выбор услуги ---

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора услуги."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "balance":
        return await show_balance(update, context)
    if data == "my_orders":
        return await show_my_orders(update, context)

    # Парсим тип услуги
    service_type_value = data.replace("service:", "")
    try:
        service_type = ServiceType(service_type_value)
    except ValueError:
        await query.edit_message_text(
            "\u274c Неизвестная услуга. Попробуйте /start",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    context.user_data["service_type"] = service_type
    service = get_service(service_type)

    body = [
        f"<b>Услуга:</b> {service.name}",
        f"<b>Описание:</b> {service.description}",
        f"<b>Стоимость:</b> {format_number(service.price)} \u20bd",
        "",
        "\U0001f4dd Отправьте текст для обработки:",
    ]
    text = _card("Новый заказ", "\U0001f4e6", body)

    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ENTER_TEXT


# --- Ввод текста ---

async def enter_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение текста от пользователя."""
    input_text = update.message.text
    context.user_data["input_text"] = input_text

    service_type = context.user_data["service_type"]
    service = get_service(service_type)

    # Показ текста для подтверждения
    preview = input_text[:200] + ("..." if len(input_text) > 200 else "")
    body = [
        f"<b>Услуга:</b> {service.name}",
        f"<b>Стоимость:</b> {format_number(service.price)} \u20bd",
        f"<b>Ваш текст:</b>",
        f"<pre>{html.escape(preview)}</pre>",
        "",
        "Подтвердите заказ:",
    ]
    text = _card("Подтверждение", "\u2705", body)

    keyboard = [
        [
            InlineKeyboardButton("\u2705 Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton("\u274c Отмена", callback_data="confirm_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )
    return CONFIRM_ORDER


# --- Подтверждение заказа ---

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка подтверждения заказа."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text(
            "\u274c Заказ отменён. Нажмите /start для нового заказа.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    user = update.effective_user
    service_type = context.user_data["service_type"]
    input_text = context.user_data["input_text"]
    service = get_service(service_type)

    # Проверка баланса
    has_funds = await billing.check_balance(user.id, service.price)
    if not has_funds:
        balance = await database.get_client_balance(user.id)
        body = [
            f"<b>Ваш баланс:</b> {format_number(balance)} \u20bd",
            f"<b>Стоимость:</b> {format_number(service.price)} \u20bd",
            f"<b>Не хватает:</b> {format_number(service.price - balance)} \u20bd",
            "",
            "Пополните баланс через администратора.",
        ]
        text = _card("Недостаточно средств", "\U0001f6ab", body)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Списываем средства
    charged = await billing.charge_client(user.id, service.price)
    if not charged:
        await query.edit_message_text(
            "\u274c Ошибка списания. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # Создаём заказ
    order_id = await database.create_order(
        client_id=user.id,
        service_type=service_type.value,
        input_text=input_text,
        price=service.price,
    )

    # Уведомляем о начале обработки
    processing_body = [
        f"<b>Заказ #{order_id}</b>",
        f"<b>Услуга:</b> {service.name}",
        "",
        f"{progress_bar(3, 10)} Обработка...",
    ]
    processing_text = _card("Обработка заказа", "\u23f3", processing_body)
    await query.edit_message_text(processing_text, parse_mode=ParseMode.HTML)

    # Обновляем статус
    await database.update_order_status(order_id, OrderStatus.PROCESSING.value)

    # Обрабатываем через AI
    result = await pipeline.process_order(service_type, input_text)

    if result:
        await database.update_order_status(
            order_id, OrderStatus.COMPLETED.value, output_text=result
        )
        # Отправляем результат
        result_body = [
            f"<b>Заказ #{order_id}</b> {status_indicator('completed')}",
            f"<b>Услуга:</b> {service.name}",
            "",
        ]
        result_card = _card("Заказ выполнен", "\U0001f389", result_body)
        await query.edit_message_text(result_card, parse_mode=ParseMode.HTML)

        # Отправляем результат отдельным сообщением
        # Разбиваем на части если текст длинный
        max_len = 4000
        for i in range(0, len(result), max_len):
            chunk = result[i:i + max_len]
            await context.bot.send_message(
                chat_id=user.id,
                text=f"<pre>{html.escape(chunk)}</pre>",
                parse_mode=ParseMode.HTML,
            )
    else:
        await database.update_order_status(order_id, OrderStatus.FAILED.value)
        # Возврат средств
        await billing.top_up_balance(user.id, service.price, method="refund")

        error_body = [
            f"<b>Заказ #{order_id}</b> {status_indicator('failed')}",
            "",
            "Произошла ошибка при обработке.",
            "Средства возвращены на баланс.",
        ]
        error_text = _card("Ошибка", "\u274c", error_body)
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)

    return ConversationHandler.END


# --- Баланс ---

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать баланс."""
    query = update.callback_query
    user = update.effective_user
    balance = await database.get_client_balance(user.id)

    body = [
        f"<b>Баланс:</b> {format_number(balance)} \u20bd",
        "",
        "Для пополнения обратитесь к администратору.",
    ]
    text = _card("Ваш баланс", "\U0001f4b0", body)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Мои заказы ---

async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать историю заказов."""
    query = update.callback_query
    user = update.effective_user
    orders = await database.get_orders_by_client(user.id, limit=5)

    if not orders:
        body = ["У вас пока нет заказов.", "", "Нажмите /start чтобы сделать заказ."]
    else:
        body = []
        for order in orders:
            body.append(
                f"{status_indicator(order['status'])} "
                f"#{order['id']} {order['service_type']} - "
                f"{format_number(order['price'])} \u20bd"
            )

    text = _card("Мои заказы", "\U0001f4cb", body)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- Отмена ---

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущей операции."""
    await update.message.reply_text(
        "\u274c Операция отменена. Нажмите /start для начала.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


def create_application() -> Application:
    """Создать и настроить приложение бота."""
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # ConversationHandler для заказа
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SERVICE: [
                CallbackQueryHandler(select_service),
            ],
            ENTER_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_text),
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    return application


def main() -> None:
    """Запуск клиентского бота."""
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

    app = create_application()
    app.run_polling()


if __name__ == "__main__":
    main()

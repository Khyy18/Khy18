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
import payment_gateway
import subscriptions
import scheduler
from models import ServiceType, OrderStatus
from services import SERVICES, get_service
from utils import _card, format_number, progress_bar, status_indicator

logger = logging.getLogger(__name__)

# Состояния ConversationHandler
SELECT_SERVICE, ENTER_TEXT, CONFIRM_ORDER = range(3)


# --- Команда /start ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветствие и показ услуг. Обрабатывает deep link для рефералов."""
    user = update.effective_user

    # Проверяем, новый ли пользователь
    existing = await database.get_or_create_client(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
    is_new = existing.get("total_spent", 0) == 0 and existing.get("balance", 0) == 0

    # Обработка реферальной deep link (ref_XXXXXX)
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0][4:])
            if is_new and referrer_id != user.id:
                await database.create_referral(
                    referrer_id=referrer_id,
                    referred_id=user.id,
                    bonus_amount=0.0,  # бонус начислится после первого заказа
                )
                logger.info(
                    "Реферал: %d привёл %d", referrer_id, user.id
                )
        except (ValueError, TypeError):
            pass

    # Карточка приветствия
    body = [
        f"Привет, <b>{html.escape(user.first_name or 'друг')}</b>!",
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
        InlineKeyboardButton("\U0001f4b3 Пополнить", callback_data="topup"),
    ])
    keyboard.append([
        InlineKeyboardButton("\U0001f4ab Подписки", callback_data="subscribe"),
        InlineKeyboardButton("\U0001f517 Реферальная ссылка", callback_data="referral"),
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
    if data == "topup":
        return await show_topup_options(update, context)
    if data == "subscribe":
        return await show_subscriptions(update, context)
    if data == "referral":
        return await show_referral(update, context)
    if data.startswith("topup_amount:"):
        return await handle_topup_amount(update, context)
    if data.startswith("sub_tier:"):
        return await handle_subscribe_tier(update, context)

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

    # Проверка возможности заказа (подписка или баланс)
    can_order = await billing.check_can_order(user.id, service.price)
    if not can_order:
        balance = await database.get_client_balance(user.id)
        body = [
            f"<b>Ваш баланс:</b> {format_number(balance)} \u20bd",
            f"<b>Стоимость:</b> {format_number(service.price)} \u20bd",
            f"<b>Не хватает:</b> {format_number(service.price - balance)} \u20bd",
            "",
            "Пополните баланс или оформите подписку.",
        ]
        text = _card("Недостаточно средств", "\U0001f6ab", body)
        keyboard = [
            [InlineKeyboardButton("\U0001f4b3 Пополнить", callback_data="topup")],
            [InlineKeyboardButton("\U0001f4ab Подписки", callback_data="subscribe")],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    # Списываем средства (подписка или баланс)
    charged = await billing.charge_or_use_subscription(user.id, service.price)
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

    # Начисляем реферальный бонус при первом заказе
    await _credit_referral_bonus(user.id, service.price)

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
        max_len = 4000
        for i in range(0, len(result), max_len):
            chunk = result[i:i + max_len]
            await context.bot.send_message(
                chat_id=user.id,
                text=f"<pre>{html.escape(chunk)}</pre>",
                parse_mode=ParseMode.HTML,
            )

        # Отправляем кнопки оценки
        rating_keyboard = [
            [
                InlineKeyboardButton(f"{star}\u2b50", callback_data=f"rate:{order_id}:{star}")
                for star in range(1, 6)
            ]
        ]
        await context.bot.send_message(
            chat_id=user.id,
            text="\U0001f4dd Оцените результат:",
            reply_markup=InlineKeyboardMarkup(rating_keyboard),
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


# --- Реферальный бонус ---

async def _credit_referral_bonus(user_id: int, order_price: float) -> None:
    """Начислить реферальный бонус реферреру при первом заказе приведённого пользователя."""
    order_count = await database.get_client_order_count(user_id)
    # Начисляем только при первом заказе (count == 1 т.к. заказ уже создан)
    if order_count != 1:
        return

    import aiosqlite
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ? AND paid = 0",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return
        referrer_id = row[0]
        bonus = order_price * config.REFERRAL_BONUS_PERCENT / 100
        # Начисляем бонус реферреру
        await db.execute(
            "UPDATE clients SET balance = balance + ? WHERE telegram_id = ?",
            (bonus, referrer_id),
        )
        await db.execute(
            "UPDATE referrals SET bonus_amount = ?, paid = 1 WHERE referred_id = ? AND referrer_id = ?",
            (bonus, user_id, referrer_id),
        )
        await db.commit()
    logger.info("Реферальный бонус %.2f начислен клиенту %d", bonus, referrer_id)


# --- Оценка заказа ---

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка оценки заказа. Если оценка <= 2, автоматически переделывает."""
    query = update.callback_query
    await query.answer()

    data = query.data  # rate:{order_id}:{stars}
    parts = data.split(":")
    if len(parts) != 3:
        return

    try:
        order_id = int(parts[1])
        rating = int(parts[2])
    except (ValueError, IndexError):
        return

    if rating < 1 or rating > 5:
        return

    # Сохраняем оценку
    await database.update_order_rating(order_id, rating)

    user = update.effective_user

    if rating >= 3:
        await query.edit_message_text(
            f"\u2b50 Спасибо за оценку ({rating}/5)! Рады, что вам понравилось.",
            parse_mode=ParseMode.HTML,
        )
    else:
        # Оценка низкая - автоматическая переделка
        await query.edit_message_text(
            f"\u2b50 Оценка {rating}/5. Мы переделаем заказ бесплатно...",
            parse_mode=ParseMode.HTML,
        )

        # Получаем данные заказа
        import aiosqlite
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            )
            order_row = await cursor.fetchone()

        if not order_row:
            return

        order = dict(order_row)
        service_type_value = order["service_type"]
        input_text = order["input_text"]

        try:
            service_type = ServiceType(service_type_value)
        except ValueError:
            return

        # Переделываем с улучшенным промптом
        improved_input = (
            "The previous result was unsatisfactory. Please improve: " + input_text
        )
        new_result = await pipeline.process_order(service_type, improved_input)

        if new_result:
            await database.update_order_status(
                order_id, OrderStatus.COMPLETED.value, output_text=new_result
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=_card("Заказ переделан", "\U0001f504", [
                    f"<b>Заказ #{order_id}</b> переделан бесплатно.",
                    "",
                ]),
                parse_mode=ParseMode.HTML,
            )
            # Отправляем новый результат
            max_len = 4000
            for i in range(0, len(new_result), max_len):
                chunk = new_result[i:i + max_len]
                await context.bot.send_message(
                    chat_id=user.id,
                    text=f"<pre>{html.escape(chunk)}</pre>",
                    parse_mode=ParseMode.HTML,
                )
        else:
            await context.bot.send_message(
                chat_id=user.id,
                text="\u274c К сожалению, переделка не удалась. Обратитесь в поддержку.",
                parse_mode=ParseMode.HTML,
            )


# --- Баланс ---

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать баланс."""
    query = update.callback_query
    user = update.effective_user
    balance = await database.get_client_balance(user.id)

    # Проверяем подписку
    sub = await subscriptions.check_subscription(user.id)
    sub_info = ""
    if sub:
        tier = sub["tier"].upper()
        orders_used = sub.get("orders_used", 0)
        sub_info = f"\n<b>Подписка:</b> {tier} (использовано заказов: {orders_used})"

    body = [
        f"<b>Баланс:</b> {format_number(balance)} \u20bd",
        sub_info,
        "",
    ]
    text = _card("Ваш баланс", "\U0001f4b0", body)

    keyboard = [
        [InlineKeyboardButton("\U0001f4b3 Пополнить баланс", callback_data="topup")],
    ]
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


# --- Пополнение баланса ---

async def show_topup_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать варианты пополнения баланса."""
    query = update.callback_query

    body = [
        "Выберите сумму пополнения:",
    ]
    text = _card("Пополнение баланса", "\U0001f4b3", body)

    amounts = [500, 1000, 2000, 5000]
    keyboard = []
    for amount in amounts:
        keyboard.append([
            InlineKeyboardButton(
                f"{format_number(amount)} \u20bd",
                callback_data=f"topup_amount:{amount}",
            )
        ])

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def handle_topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора суммы пополнения, создание платежа."""
    query = update.callback_query

    amount_str = query.data.replace("topup_amount:", "")
    try:
        amount = int(amount_str)
    except ValueError:
        return ConversationHandler.END

    user = update.effective_user

    # Создаём платёж через YooKassa
    payment_url = await payment_gateway.create_payment(
        client_id=user.id,
        amount=float(amount),
        description=f"Пополнение баланса на {amount} руб.",
    )

    if payment_url:
        body = [
            f"<b>Сумма:</b> {format_number(amount)} \u20bd",
            "",
            "Нажмите кнопку ниже для оплаты:",
        ]
        text = _card("Оплата", "\U0001f4b3", body)
        keyboard = [
            [InlineKeyboardButton("\U0001f4b3 Оплатить", url=payment_url)],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
    else:
        await query.edit_message_text(
            "\u274c Ошибка создания платежа. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )

    return ConversationHandler.END


# --- Подписки ---

async def show_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать тарифы подписок."""
    query = update.callback_query

    body = [
        "<b>BASIC</b> \u2014 {} \u20bd/мес".format(format_number(config.SUBSCRIPTION_BASIC_PRICE)),
        f"  \u2022 {config.SUBSCRIPTION_BASIC_ORDERS} заказов в месяц",
        f"  \u2022 Приоритетная обработка",
        "",
        "<b>PRO</b> \u2014 {} \u20bd/мес".format(format_number(config.SUBSCRIPTION_PRO_PRICE)),
        f"  \u2022 Безлимитные заказы",
        f"  \u2022 Приоритетная обработка",
        f"  \u2022 Персональный менеджер",
    ]
    text = _card("Подписки", "\U0001f4ab", body)

    keyboard = [
        [InlineKeyboardButton(
            f"BASIC - {format_number(config.SUBSCRIPTION_BASIC_PRICE)} \u20bd",
            callback_data="sub_tier:basic",
        )],
        [InlineKeyboardButton(
            f"PRO - {format_number(config.SUBSCRIPTION_PRO_PRICE)} \u20bd",
            callback_data="sub_tier:pro",
        )],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def handle_subscribe_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора тарифа подписки."""
    query = update.callback_query

    tier = query.data.replace("sub_tier:", "")
    user = update.effective_user

    if tier == "basic":
        amount = config.SUBSCRIPTION_BASIC_PRICE
    elif tier == "pro":
        amount = config.SUBSCRIPTION_PRO_PRICE
    else:
        return ConversationHandler.END

    # Создаём платёж подписки
    payment_url = await payment_gateway.create_subscription_payment(
        client_id=user.id,
        tier=tier,
        amount=float(amount),
    )

    if payment_url:
        body = [
            f"<b>Тариф:</b> {tier.upper()}",
            f"<b>Стоимость:</b> {format_number(amount)} \u20bd/мес",
            "",
            "Нажмите кнопку ниже для оплаты:",
        ]
        text = _card("Оформление подписки", "\U0001f4ab", body)
        keyboard = [
            [InlineKeyboardButton("\U0001f4b3 Оплатить", url=payment_url)],
        ]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
    else:
        await query.edit_message_text(
            "\u274c Ошибка создания платежа. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )

    return ConversationHandler.END


# --- Реферальная ссылка ---

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать реферальную ссылку и статистику."""
    query = update.callback_query
    user = update.effective_user

    ref_link = f"https://t.me/{config.BOT_USERNAME}?start=ref_{user.id}"
    stats = await database.get_referral_stats(user.id)

    body = [
        "<b>Ваша реферальная ссылка:</b>",
        f"<code>{ref_link}</code>",
        "",
        f"<b>Приглашено:</b> {stats['total']} чел.",
        f"<b>Заработано:</b> {format_number(stats['total_bonus'])} \u20bd",
        "",
        f"Приглашайте друзей и получайте {config.REFERRAL_BONUS_PERCENT}% "
        f"от их первого заказа!",
    ]
    text = _card("Реферальная программа", "\U0001f517", body)

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
            rating_str = f" [{order['rating']}\u2b50]" if order.get('rating') else ""
            body.append(
                f"{status_indicator(order['status'])} "
                f"#{order['id']} {order['service_type']} - "
                f"{format_number(order['price'])} \u20bd{rating_str}"
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


# --- Post-init: запуск планировщика ---

async def post_init(application: Application) -> None:
    """Вызывается после инициализации приложения. Запускает планировщик."""
    scheduler.start_scheduler(application.bot)


def create_application() -> Application:
    """Создать и настроить приложение бота."""
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

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

    # Обработчик оценки (вне ConversationHandler)
    application.add_handler(
        CallbackQueryHandler(handle_rating, pattern=r"^rate:\d+:\d+$")
    )

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

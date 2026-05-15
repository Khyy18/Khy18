"""Клиентский Telegram-бот AI-агентства (python-telegram-bot v20+)."""

import asyncio
import html
import logging
import sys

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
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
import pricing
import i18n
import document_generator
import ab_testing
from models import ServiceType, OrderStatus
from services import SERVICES, get_service
from utils import _card, format_number, progress_bar, status_indicator

# Интеграция promo (graceful)
try:
    import promo as promo_module
except ImportError:
    promo_module = None

# Интеграция reviews (graceful)
try:
    import reviews as reviews_module
except ImportError:
    reviews_module = None

# Интеграция ad_manager (graceful)
try:
    import ad_manager
except ImportError:
    ad_manager = None

# Интеграция rate_limiter и telegram_payments (graceful)
try:
    from rate_limiter import RateLimiter
    _rate_limiter = RateLimiter()
except ImportError:
    _rate_limiter = None

try:
    import telegram_payments
except ImportError:
    telegram_payments = None

try:
    from queue_manager import OrderQueue
    _order_queue: "OrderQueue | None" = None
except ImportError:
    _order_queue = None

# Интеграция voice_handler (graceful)
try:
    import voice_handler as voice_handler_module
except ImportError:
    voice_handler_module = None

# Интеграция vision_handler (graceful)
try:
    import vision_handler as vision_handler_module
except ImportError:
    vision_handler_module = None

# Интеграция upsell_agent (graceful)
try:
    import upsell_agent as upsell_agent_module
except ImportError:
    upsell_agent_module = None

# Интеграция marketplace (graceful)
try:
    import marketplace as marketplace_module
except ImportError:
    marketplace_module = None

# Интеграция whitelabel (graceful)
try:
    import whitelabel as whitelabel_module
except ImportError:
    whitelabel_module = None

# Интеграция onboarding (graceful)
try:
    import onboarding as onboarding_module
except ImportError:
    onboarding_module = None

# Интеграция retargeting (graceful)
try:
    import retargeting as retargeting_module
except ImportError:
    retargeting_module = None

# Интеграция demand_pricing (graceful)
try:
    import demand_pricing as demand_pricing_module
except ImportError:
    demand_pricing_module = None


def set_order_queue(queue) -> None:
    """Set the shared order queue instance (called from main_multi.py)."""
    global _order_queue
    _order_queue = queue

logger = logging.getLogger(__name__)

# Состояния ConversationHandler
SELECT_SERVICE, ENTER_TEXT, SELECT_URGENCY, CONFIRM_ORDER = range(4)


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

    # Получаем язык клиента
    lang = await database.get_client_language(user.id)

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

    # Обработка рекламной deep link (ad_SOURCE)
    if context.args and context.args[0].startswith("ad_"):
        source = context.args[0][3:]
        if ad_manager:
            try:
                await ad_manager.track_utm(user.id, source)
            except Exception as e:
                logger.debug("Ошибка трекинга UTM: %s", e)

    # Трекинг ретаргетинга - пользователь выполнил /start
    if retargeting_module:
        try:
            await retargeting_module.track_event(user.id, "start")
        except Exception as e:
            logger.debug("Ошибка трекинга retargeting: %s", e)

    # Онбординг для новых пользователей
    if is_new and onboarding_module:
        try:
            return await onboarding_module.start_onboarding(update, context)
        except Exception as e:
            logger.debug("Ошибка онбординга: %s", e)

    # Проверка бесплатного триала
    trial_available = await billing.check_free_trial(user.id)

    # Карточка приветствия с персоной
    name = html.escape(user.first_name or "друг")
    body = [
        i18n.get_text(lang, "persona_greeting", greeting=config.BOT_PERSONA_GREETING),
        "",
        i18n.get_text(lang, "welcome", name=name),
        "",
        i18n.get_text(lang, "service_list"),
    ]
    if trial_available:
        body.insert(2, i18n.get_text(lang, "first_order_free"))

    welcome = _card(config.BOT_PERSONA_NAME, "\U0001f916", body)

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

    # Кнопка маркетплейса
    if marketplace_module:
        keyboard.append([
            InlineKeyboardButton("\U0001f6cd Маркетплейс", callback_data="marketplace"),
        ])

    # WebAppInfo button for Mini App
    if config.MINI_APP_URL:
        keyboard.append([
            InlineKeyboardButton(
                "\U0001f4f1 Open App",
                web_app=WebAppInfo(url=config.MINI_APP_URL),
            ),
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
    if data.startswith("topup_stars:"):
        return await handle_topup_stars(update, context)
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
    """Получение текста от пользователя, предложить выбор срочности."""
    input_text = update.message.text
    context.user_data["input_text"] = input_text

    user = update.effective_user

    # Записываем сообщение в rate limiter
    if _rate_limiter:
        _rate_limiter.record_message(user.id)

    lang = await database.get_client_language(user.id)
    service_type = context.user_data["service_type"]
    service = get_service(service_type)

    # Рассчитываем цены для обоих вариантов срочности
    normal_price = pricing.calculate_price(service_type.value, len(input_text), urgent=False)
    urgent_price = pricing.calculate_price(service_type.value, len(input_text), urgent=True)

    body = [
        f"<b>Услуга:</b> {service.name}",
        f"<b>Обычный:</b> {format_number(normal_price)} \u20bd",
        f"<b>Срочный:</b> {format_number(urgent_price)} \u20bd",
        "",
        i18n.get_text(lang, "urgency_prompt"),
    ]
    text = _card("Срочность", "\u23f0", body)

    keyboard = [
        [
            InlineKeyboardButton(
                i18n.get_text(lang, "urgency_normal"),
                callback_data="urgency:normal",
            ),
            InlineKeyboardButton(
                i18n.get_text(lang, "urgency_urgent"),
                callback_data="urgency:urgent",
            ),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )
    return SELECT_URGENCY


# --- Выбор срочности ---

async def select_urgency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора срочности, показ подтверждения."""
    query = update.callback_query
    await query.answer()

    data = query.data  # urgency:normal или urgency:urgent
    urgent = data == "urgency:urgent"
    context.user_data["urgent"] = urgent

    user = update.effective_user
    lang = await database.get_client_language(user.id)
    service_type = context.user_data["service_type"]
    input_text = context.user_data["input_text"]
    service = get_service(service_type)

    # Рассчитываем динамическую цену
    price = pricing.calculate_price(service_type.value, len(input_text), urgent=urgent)
    context.user_data["calculated_price"] = price

    # Показ текста для подтверждения
    preview = input_text[:200] + ("..." if len(input_text) > 200 else "")
    urgency_label = i18n.get_text(lang, "urgency_urgent") if urgent else i18n.get_text(lang, "urgency_normal")
    body = [
        f"<b>Услуга:</b> {service.name}",
        f"<b>Срочность:</b> {urgency_label}",
        f"<b>Стоимость:</b> {format_number(price)} \u20bd",
        f"<b>Ваш текст:</b>",
        f"<pre>{html.escape(preview)}</pre>",
        "",
        i18n.get_text(lang, "confirm_order"),
    ]
    text = _card("Подтверждение", "\u2705", body)

    keyboard = [
        [
            InlineKeyboardButton("\u2705 Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton("\u274c Отмена", callback_data="confirm_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
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

    # Проверка rate limit перед обработкой заказа
    if _rate_limiter:
        allowed, limit_msg = _rate_limiter.check_rate_limit(user.id)
        if not allowed:
            await query.edit_message_text(
                f"\u23f3 {limit_msg}\n\nПопробуйте позже.",
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

    lang = await database.get_client_language(user.id)
    service_type = context.user_data["service_type"]
    input_text = context.user_data["input_text"]
    service = get_service(service_type)

    # Используем динамическую цену
    price = context.user_data.get("calculated_price", service.price)

    # Применяем промокод если установлен
    promo_code = context.user_data.get("promo_code")
    if promo_code and promo_module:
        try:
            discounted_price, promo_data = await promo_module.apply_promo(promo_code, price)
            if promo_data:
                price = discounted_price
                logger.info("Промокод %s применён, новая цена: %.2f", promo_code, price)
        except Exception as e:
            logger.warning("Ошибка применения промокода: %s", e)

    # Проверка бесплатного триала
    is_free_trial = await billing.check_free_trial(user.id)

    if not is_free_trial:
        # Проверка возможности заказа (подписка или баланс)
        can_order = await billing.check_can_order(user.id, price)
        if not can_order:
            balance = await database.get_client_balance(user.id)
            body = [
                f"<b>Ваш баланс:</b> {format_number(balance)} \u20bd",
                f"<b>Стоимость:</b> {format_number(price)} \u20bd",
                f"<b>Не хватает:</b> {format_number(price - balance)} \u20bd",
                "",
                i18n.get_text(lang, "insufficient_funds"),
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
        charged = await billing.charge_or_use_subscription(user.id, price)
        if not charged:
            balance = await database.get_client_balance(user.id)
            body = [
                f"<b>Ваш баланс:</b> {format_number(balance)} \u20bd",
                f"<b>Стоимость:</b> {format_number(price)} \u20bd",
                "",
                i18n.get_text(lang, "insufficient_funds"),
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

    # Создаём заказ
    order_id = await database.create_order(
        client_id=user.id,
        service_type=service_type.value,
        input_text=input_text,
        price=0.0 if is_free_trial else price,
    )

    # Записываем заказ в rate limiter
    if _rate_limiter:
        _rate_limiter.record_order(user.id)

    # Если это бесплатный триал - отмечаем использованным
    if is_free_trial:
        await billing.mark_free_trial_used(user.id)

    # Начисляем реферальный бонус при первом заказе
    await _credit_referral_bonus(user.id, price)

    # Уведомляем о начале обработки
    processing_body = [
        f"<b>Заказ #{order_id}</b>",
        f"<b>Услуга:</b> {service.name}",
        "",
        f"{progress_bar(3, 10)} {i18n.get_text(lang, 'order_processing')}",
    ]
    processing_text = _card("Обработка заказа", "\u23f3", processing_body)
    await query.edit_message_text(processing_text, parse_mode=ParseMode.HTML)

    # Обновляем статус
    await database.update_order_status(order_id, OrderStatus.PROCESSING.value)

    # Обрабатываем через AI (через очередь если доступна, иначе inline)
    if _order_queue and _order_queue._running:
        # Используем очередь для обработки
        priority = 0 if context.user_data.get("urgent") else 1
        wait_time = await _order_queue.enqueue_order(
            order_id=order_id,
            service_type=service_type.value,
            input_text=input_text,
            priority=priority,
        )
        if wait_time is not None:
            # Очередь полна - обрабатываем inline
            result, variant_id = await pipeline.process_order(service_type, input_text)
        else:
            # Заказ в очереди - ждём результат (polling)
            import time as _time
            _start = _time.time()
            result = None
            variant_id = None
            while _time.time() - _start < 120:  # макс 2 минуты
                await asyncio.sleep(2)
                order_data = await database.get_order_by_id(order_id)
                if order_data and order_data["status"] in ("completed", "failed"):
                    result = order_data.get("output_text")
                    variant_id = order_data.get("ab_variant_id")
                    break
            else:
                # Таймаут - проверяем последний статус
                order_data = await database.get_order_by_id(order_id)
                result = order_data.get("output_text") if order_data else None
                variant_id = order_data.get("ab_variant_id") if order_data else None
    else:
        result, variant_id = await pipeline.process_order(service_type, input_text)

    if result:
        await database.update_order_status(
            order_id, OrderStatus.COMPLETED.value, output_text=result
        )
        # Сохраняем variant_id если был A/B тест
        if variant_id is not None:
            await database.update_order_ab_variant(order_id, variant_id)
        # Отправляем результат
        result_body = [
            f"<b>Заказ #{order_id}</b> {status_indicator('completed')}",
            f"<b>Услуга:</b> {service.name}",
            "",
        ]
        result_card = _card(i18n.get_text(lang, "order_completed"), "\U0001f389", result_body)
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

        # Кнопки скачивания документов
        download_keyboard = [
            [
                InlineKeyboardButton(
                    i18n.get_text(lang, "download_docx"),
                    callback_data=f"download:{order_id}:docx",
                ),
                InlineKeyboardButton(
                    i18n.get_text(lang, "download_pdf"),
                    callback_data=f"download:{order_id}:pdf",
                ),
            ]
        ]
        await context.bot.send_message(
            chat_id=user.id,
            text="\U0001f4e5 Скачать результат:",
            reply_markup=InlineKeyboardMarkup(download_keyboard),
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
            text=i18n.get_text(lang, "rate_prompt"),
            reply_markup=InlineKeyboardMarkup(rating_keyboard),
            parse_mode=ParseMode.HTML,
        )

        # Record whitelabel revenue if this is a whitelabel bot
        if whitelabel_module and context.bot_data.get("whitelabel_bot_id"):
            try:
                bot_id = context.bot_data["whitelabel_bot_id"]
                revenue_share = context.bot_data.get("whitelabel_revenue_share", 0.3)
                await whitelabel_module.record_whitelabel_revenue(
                    bot_id=bot_id,
                    order_id=order_id,
                    amount=price,
                    revenue_share=revenue_share,
                )
            except Exception as e:
                logger.warning("Ошибка записи whitelabel revenue: %s", e)
    else:
        await database.update_order_status(order_id, OrderStatus.FAILED.value)
        # Возврат средств (только если не бесплатный триал)
        if not is_free_trial:
            await billing.top_up_balance(user.id, price, method="refund")

        error_body = [
            f"<b>Заказ #{order_id}</b> {status_indicator('failed')}",
            "",
            i18n.get_text(lang, "order_failed"),
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

    bonus = await database.credit_referral_bonus(
        user_id, order_price, config.REFERRAL_BONUS_PERCENT
    )
    if bonus is not None:
        logger.info("Реферальный бонус %.2f начислен за клиента %d", bonus, user_id)


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

    # Проверка владельца заказа
    order = await database.get_order_by_id(order_id)
    user = update.effective_user
    if not order or order.get("client_id") != user.id:
        await query.edit_message_text(
            "\u274c Это не ваш заказ.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Сохраняем оценку
    await database.update_order_rating(order_id, rating)

    # Записываем результат A/B теста если был использован вариант
    if order.get("ab_variant_id"):
        try:
            await ab_testing.record_result(order["ab_variant_id"], rating)
        except Exception as e:
            logger.warning("Ошибка записи результата A/B теста: %s", e)

    if rating >= 3:
        await query.edit_message_text(
            f"\u2b50 Спасибо за оценку ({rating}/5)! Рады, что вам понравилось.",
            parse_mode=ParseMode.HTML,
        )
        # Prompt for text review after high rating (4-5)
        if rating >= 4 and reviews_module:
            review_keyboard = [
                [InlineKeyboardButton(
                    "\U0001f4dd Оставить отзыв",
                    callback_data=f"review:{order_id}",
                )],
            ]
            await context.bot.send_message(
                chat_id=user.id,
                text="\U0001f4ac Хотите оставить текстовый отзыв? Это поможет другим клиентам!",
                reply_markup=InlineKeyboardMarkup(review_keyboard),
                parse_mode=ParseMode.HTML,
            )
    else:
        # Оценка низкая - автоматическая переделка
        await query.edit_message_text(
            f"\u2b50 Оценка {rating}/5. Мы переделаем заказ бесплатно...",
            parse_mode=ParseMode.HTML,
        )

        # Получаем данные заказа
        order = await database.get_order_by_id(order_id)

        if not order:
            return
        service_type_value = order["service_type"]
        input_text = order["input_text"]

        try:
            service_type = ServiceType(service_type_value)
        except ValueError:
            return

        # Переделываем с улучшенным промптом
        improved_input = (
            "Предыдущий результат неудовлетворительный. Пожалуйста, улучшите текст: " + input_text
        )
        new_result, _ = await pipeline.process_order(service_type, improved_input)

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

    # Кнопка оплаты через Telegram Stars
    if telegram_payments:
        keyboard.append([
            InlineKeyboardButton(
                "\u2b50 Оплатить через Telegram Stars",
                callback_data="topup_stars:100",
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


# --- Оплата через Telegram Stars ---

async def handle_topup_stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка оплаты через Telegram Stars."""
    query = update.callback_query
    user = update.effective_user

    stars_str = query.data.replace("topup_stars:", "")
    try:
        stars_amount = int(stars_str)
    except ValueError:
        stars_amount = 100

    if telegram_payments:
        rub_equivalent = int(stars_amount * config.STARS_TO_RUB_RATE)
        await telegram_payments.create_stars_invoice(
            chat_id=user.id,
            title=f"Пополнение баланса",
            description=f"Пополнение на {rub_equivalent} руб. ({stars_amount} Stars)",
            price_stars=stars_amount,
            payload=f"topup_{user.id}_{stars_amount}",
            bot=context.bot,
        )
        await query.edit_message_text(
            "\u2b50 Инвойс для оплаты Stars отправлен!",
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.edit_message_text(
            "\u274c Оплата через Stars временно недоступна.",
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


# --- Скачивание документов ---

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка скачивания документа (.docx или .pdf)."""
    query = update.callback_query
    await query.answer()

    data = query.data  # download:{order_id}:{format}
    parts = data.split(":")
    if len(parts) != 3:
        return

    try:
        order_id = int(parts[1])
        fmt = parts[2]
    except (ValueError, IndexError):
        return

    if fmt not in ("docx", "pdf"):
        return

    # Получаем заказ
    order = await database.get_order_by_id(order_id)
    if not order or not order.get("output_text"):
        await query.edit_message_text(
            "\u274c Результат заказа не найден.",
            parse_mode=ParseMode.HTML,
        )
        return

    user = update.effective_user

    # Проверка владельца заказа
    if order.get("client_id") != user.id:
        await query.edit_message_text(
            "\u274c Это не ваш заказ.",
            parse_mode=ParseMode.HTML,
        )
        return
    service_type_value = order["service_type"]
    try:
        service_type = ServiceType(service_type_value)
        service = get_service(service_type)
        service_name = service.name
    except (ValueError, KeyError):
        service_name = service_type_value

    result_text = order["output_text"]
    date = order.get("completed_at") or order.get("created_at", "")

    try:
        if fmt == "docx":
            filepath = await document_generator.generate_docx(
                order_id, service_name, result_text, date
            )
        else:
            filepath = await document_generator.generate_pdf(
                order_id, service_name, result_text, date
            )

        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename=f"order_{order_id}.{fmt}",
            )

        # Удаляем временный файл после отправки
        import os as _os
        try:
            _os.unlink(filepath)
        except OSError:
            pass
    except Exception as e:
        logger.error("Ошибка генерации документа: %s", e)
        await context.bot.send_message(
            chat_id=user.id,
            text="\u274c Ошибка генерации документа. Попробуйте позже.",
            parse_mode=ParseMode.HTML,
        )


# --- Команда /lang ---

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переключение языка интерфейса."""
    user = update.effective_user
    current_lang = await database.get_client_language(user.id)

    # Переключаем
    new_lang = "en" if current_lang == "ru" else "ru"
    await database.set_client_language(user.id, new_lang)

    text = i18n.get_text(new_lang, "lang_set")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# --- Команда /promo ---

async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Применить промокод: /promo CODE."""
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "\U0001f3ab Введите промокод: /promo КОД",
            parse_mode=ParseMode.HTML,
        )
        return

    code = context.args[0].strip()

    if not promo_module:
        await update.message.reply_text(
            "\u274c Промокоды временно недоступны.",
            parse_mode=ParseMode.HTML,
        )
        return

    promo_data = await promo_module.validate_promo(code)
    if promo_data:
        context.user_data["promo_code"] = code.upper()
        discount_info = (
            f"{int(promo_data['discount_value'])}%"
            if promo_data["discount_type"] == "percentage"
            else f"{format_number(promo_data['discount_value'])} \u20bd"
        )
        body = [
            f"<b>Промокод:</b> {code.upper()}",
            f"<b>Скидка:</b> {discount_info}",
            "",
            "Скидка будет применена к следующему заказу.",
        ]
        text = _card("Промокод активирован", "\u2705", body)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            "\u274c Промокод недействителен или истёк.",
            parse_mode=ParseMode.HTML,
        )


# --- Обработка запроса на отзыв ---

async def handle_review_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle review prompt button click - ask user to type review text."""
    query = update.callback_query
    await query.answer()

    data = query.data  # review:{order_id}
    parts = data.split(":")
    if len(parts) != 2:
        return

    try:
        order_id = int(parts[1])
    except (ValueError, IndexError):
        return

    context.user_data["review_order_id"] = order_id
    await query.edit_message_text(
        "\U0001f4dd Напишите ваш отзыв (одним сообщением):",
        parse_mode=ParseMode.HTML,
    )


async def handle_review_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle review text submission."""
    order_id = context.user_data.get("review_order_id")
    if not order_id:
        return

    user = update.effective_user
    text = update.message.text

    if reviews_module:
        # Get order rating
        order = await database.get_order_by_id(order_id)
        rating = order.get("rating", 5) if order else 5

        review_id = await reviews_module.submit_review(
            client_id=user.id,
            order_id=order_id,
            text=text,
            rating=rating,
        )
        if review_id:
            await update.message.reply_text(
                "\u2705 Спасибо за отзыв! Он будет опубликован после модерации.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                "\u274c Отзыв не прошёл модерацию. Попробуйте другой текст.",
                parse_mode=ParseMode.HTML,
            )

    # Clear the state
    context.user_data.pop("review_order_id", None)


# --- Отмена ---

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущей операции."""
    user = update.effective_user
    lang = await database.get_client_language(user.id)
    await update.message.reply_text(
        f"\u274c {i18n.get_text(lang, 'cancel')}",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# --- Post-init: запуск планировщика ---

async def _handle_voice_confirmation_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper для обработки подтверждения голосового ввода."""
    if voice_handler_module:
        result = await voice_handler_module.handle_voice_confirmation(update, context)
        # If confirmed and input_text is set, proceed to urgency selection
        if result == ENTER_TEXT and context.user_data.get("input_text"):
            # Simulate what enter_text does: show urgency selection
            user = update.effective_user
            lang = await database.get_client_language(user.id)
            service_type = context.user_data["service_type"]
            input_text = context.user_data["input_text"]
            service = get_service(service_type)

            normal_price = pricing.calculate_price(service_type.value, len(input_text), urgent=False)
            urgent_price = pricing.calculate_price(service_type.value, len(input_text), urgent=True)

            body = [
                f"<b>Услуга:</b> {service.name}",
                f"<b>Обычный:</b> {format_number(normal_price)} \u20bd",
                f"<b>Срочный:</b> {format_number(urgent_price)} \u20bd",
                "",
                i18n.get_text(lang, "urgency_prompt"),
            ]
            text = _card("Срочность", "\u23f0", body)

            keyboard = [
                [
                    InlineKeyboardButton(
                        i18n.get_text(lang, "urgency_normal"),
                        callback_data="urgency:normal",
                    ),
                    InlineKeyboardButton(
                        i18n.get_text(lang, "urgency_urgent"),
                        callback_data="urgency:urgent",
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            query = update.callback_query
            await query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
            return SELECT_URGENCY
        return result
    # If module unavailable, just stay in ENTER_TEXT
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "\u274c Голосовой ввод временно недоступен.",
        parse_mode=ParseMode.HTML,
    )
    return ENTER_TEXT


async def _handle_voice_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper для обработки голосовых сообщений."""
    if voice_handler_module:
        return await voice_handler_module.handle_voice(update, context)
    # Если модуль недоступен, сообщаем пользователю
    await update.message.reply_text(
        "\u274c Голосовой ввод временно недоступен. Отправьте текст.",
        parse_mode=ParseMode.HTML,
    )
    return ENTER_TEXT


async def _handle_photo_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Wrapper для обработки фото."""
    if vision_handler_module:
        return await vision_handler_module.handle_photo(update, context)
    await update.message.reply_text(
        "\u274c Распознавание фото временно недоступно. Отправьте текст.",
        parse_mode=ParseMode.HTML,
    )
    return ENTER_TEXT


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
                CallbackQueryHandler(
                    _handle_voice_confirmation_wrapper,
                    pattern=r"^voice_(confirm|cancel)$",
                ),
                MessageHandler(filters.VOICE | filters.AUDIO, _handle_voice_wrapper),
                MessageHandler(filters.PHOTO, _handle_photo_wrapper),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_text),
            ],
            SELECT_URGENCY: [
                CallbackQueryHandler(select_urgency),
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

    # Обработчик скачивания документов
    application.add_handler(
        CallbackQueryHandler(handle_download, pattern=r"^download:\d+:(docx|pdf)$")
    )

    # Обработчик запроса на отзыв
    application.add_handler(
        CallbackQueryHandler(handle_review_prompt, pattern=r"^review:\d+$")
    )

    # Обработчик текста отзыва (фильтруем только когда есть review_order_id)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_review_text,
        ),
        group=1,
    )

    # Команда /lang
    application.add_handler(CommandHandler("lang", lang_command))

    # Команда /promo
    application.add_handler(CommandHandler("promo", promo_command))

    # Регистрация обработчиков Telegram Stars платежей
    if telegram_payments:
        telegram_payments.register_payment_handlers(application)

    # Обработчики маркетплейса
    if marketplace_module:
        application.add_handler(
            CallbackQueryHandler(marketplace_module.show_marketplace, pattern=r"^marketplace$")
        )
        application.add_handler(
            CallbackQueryHandler(marketplace_module.show_category, pattern=r"^mkt_cat:")
        )
        application.add_handler(
            CallbackQueryHandler(marketplace_module.show_template_preview, pattern=r"^mkt_tpl:\d+$")
        )
        application.add_handler(
            CallbackQueryHandler(marketplace_module.handle_purchase, pattern=r"^mkt_buy:\d+$")
        )

    # Обработчики upsell
    if upsell_agent_module:
        application.add_handler(
            CallbackQueryHandler(upsell_agent_module.handle_upsell_purchase, pattern=r"^upsell:")
        )
        application.add_handler(
            CallbackQueryHandler(upsell_agent_module.handle_upsell_purchase, pattern=r"^upsell_skip$")
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

"""Фабрика для создания нишевых Telegram-ботов с ограниченным набором услуг."""

import html
import logging
from typing import Dict, List

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

import database
import billing
import pipeline
import pricing
import i18n
import document_generator
import ab_testing
from models import ServiceType, OrderStatus
from services import SERVICES, ServiceDefinition, get_service
from utils import _card, format_number, progress_bar, status_indicator

logger = logging.getLogger(__name__)

# Состояния ConversationHandler
SELECT_SERVICE, ENTER_TEXT, SELECT_URGENCY, CONFIRM_ORDER = range(4)


def _get_filtered_services(service_types: List[str]) -> Dict[ServiceType, ServiceDefinition]:
    """Получить отфильтрованный словарь сервисов по списку типов."""
    filtered = {}
    for stype_str in service_types:
        try:
            stype = ServiceType(stype_str)
            if stype in SERVICES:
                filtered[stype] = SERVICES[stype]
        except ValueError:
            logger.warning("Unknown service type: %s", stype_str)
    return filtered


def create_bot_application(
    token: str,
    name: str,
    service_types: List[str],
    persona_name: str,
) -> Application:
    """
    Создать Application для нишевого бота с ограниченным набором услуг.

    Args:
        token: Telegram Bot API токен
        name: имя бота (для логирования)
        service_types: список типов услуг (значения ServiceType enum)
        persona_name: имя персоны бота

    Returns:
        Сконфигурированный Application
    """
    filtered_services = _get_filtered_services(service_types)

    async def post_init(application: Application) -> None:
        """Инициализация bot_data с конфигурацией."""
        application.bot_data["name"] = name
        application.bot_data["persona_name"] = persona_name
        application.bot_data["services"] = filtered_services

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Приветствие и показ доступных услуг нишевого бота."""
        user = update.effective_user
        services = context.application.bot_data.get("services", filtered_services)
        bot_persona = context.application.bot_data.get("persona_name", persona_name)

        await database.get_or_create_client(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

        lang = await database.get_client_language(user.id)
        user_name = html.escape(user.first_name or "друг")

        body = [
            f"Привет, {user_name}! Я {bot_persona}.",
            "",
            i18n.get_text(lang, "service_list"),
        ]
        welcome = _card(bot_persona, "\U0001f916", body)

        keyboard = []
        for stype, sdef in services.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{sdef.name} - {format_number(sdef.price)} \u20bd",
                    callback_data=f"service:{stype.value}",
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            welcome, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
        return SELECT_SERVICE

    async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора услуги."""
        query = update.callback_query
        await query.answer()

        data = query.data
        service_type_value = data.replace("service:", "")
        services = context.application.bot_data.get("services", filtered_services)

        try:
            service_type = ServiceType(service_type_value)
        except ValueError:
            await query.edit_message_text(
                "\u274c Неизвестная услуга. Попробуйте /start",
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        if service_type not in services:
            await query.edit_message_text(
                "\u274c Эта услуга недоступна. Попробуйте /start",
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        context.user_data["service_type"] = service_type
        service = services[service_type]

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

    async def enter_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение текста, предложить выбор срочности."""
        input_text = update.message.text
        context.user_data["input_text"] = input_text

        user = update.effective_user
        lang = await database.get_client_language(user.id)
        service_type = context.user_data["service_type"]
        services = context.application.bot_data.get("services", filtered_services)
        service = services[service_type]

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

    async def select_urgency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора срочности."""
        query = update.callback_query
        await query.answer()

        urgent = query.data == "urgency:urgent"
        context.user_data["urgent"] = urgent

        user = update.effective_user
        lang = await database.get_client_language(user.id)
        service_type = context.user_data["service_type"]
        input_text = context.user_data["input_text"]
        services = context.application.bot_data.get("services", filtered_services)
        service = services[service_type]

        price = pricing.calculate_price(service_type.value, len(input_text), urgent=urgent)
        context.user_data["calculated_price"] = price

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
        lang = await database.get_client_language(user.id)
        service_type = context.user_data["service_type"]
        input_text = context.user_data["input_text"]
        services = context.application.bot_data.get("services", filtered_services)
        service = services[service_type]

        price = context.user_data.get("calculated_price", service.price)

        # Проверка бесплатного триала
        is_free_trial = await billing.check_free_trial(user.id)

        if not is_free_trial:
            # Проверка баланса
            can_order = await billing.check_can_order(user.id, price)
            if not can_order:
                balance = await database.get_client_balance(user.id)
                body = [
                    f"<b>Ваш баланс:</b> {format_number(balance)} \u20bd",
                    f"<b>Стоимость:</b> {format_number(price)} \u20bd",
                    "",
                    i18n.get_text(lang, "insufficient_funds"),
                ]
                text = _card("Недостаточно средств", "\U0001f6ab", body)
                await query.edit_message_text(text, parse_mode=ParseMode.HTML)
                return ConversationHandler.END

            charged = await billing.charge_or_use_subscription(user.id, price)
            if not charged:
                await query.edit_message_text(
                    "\u274c Ошибка списания. Попробуйте позже.",
                    parse_mode=ParseMode.HTML,
                )
                return ConversationHandler.END

        # Создаем заказ
        order_id = await database.create_order(
            client_id=user.id,
            service_type=service_type.value,
            input_text=input_text,
            price=0.0 if is_free_trial else price,
        )

        # Если это бесплатный триал - отмечаем использованным
        if is_free_trial:
            await billing.mark_free_trial_used(user.id)

        # Уведомляем о начале обработки
        processing_body = [
            f"<b>Заказ #{order_id}</b>",
            f"<b>Услуга:</b> {service.name}",
            "",
            f"{progress_bar(3, 10)} {i18n.get_text(lang, 'order_processing')}",
        ]
        processing_text = _card("Обработка заказа", "\u23f3", processing_body)
        await query.edit_message_text(processing_text, parse_mode=ParseMode.HTML)

        await database.update_order_status(order_id, OrderStatus.PROCESSING.value)

        # Обрабатываем через AI
        result, variant_id = await pipeline.process_order(service_type, input_text)

        if result:
            await database.update_order_status(
                order_id, OrderStatus.COMPLETED.value, output_text=result
            )
            if variant_id is not None:
                await database.update_order_ab_variant(order_id, variant_id)

            result_body = [
                f"<b>Заказ #{order_id}</b> {status_indicator('completed')}",
                f"<b>Услуга:</b> {service.name}",
                "",
            ]
            result_card = _card(i18n.get_text(lang, "order_completed"), "\U0001f389", result_body)
            await query.edit_message_text(result_card, parse_mode=ParseMode.HTML)

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

            # Кнопки оценки
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

    async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка оценки заказа."""
        query = update.callback_query
        await query.answer()

        parts = query.data.split(":")
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

        await database.update_order_rating(order_id, rating)

        if order.get("ab_variant_id"):
            try:
                await ab_testing.record_result(order["ab_variant_id"], rating)
            except Exception as e:
                logger.warning("A/B test result error: %s", e)

        if rating >= 3:
            await query.edit_message_text(
                f"\u2b50 Спасибо за оценку ({rating}/5)!",
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.edit_message_text(
                f"\u2b50 Оценка {rating}/5. Спасибо за обратную связь.",
                parse_mode=ParseMode.HTML,
            )

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена текущей операции."""
        await update.message.reply_text(
            "\u274c Отменено. Нажмите /start",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка скачивания документа (.docx или .pdf)."""
        query = update.callback_query
        await query.answer()

        parts = query.data.split(":")
        if len(parts) != 3:
            return
        try:
            order_id = int(parts[1])
            fmt = parts[2]
        except (ValueError, IndexError):
            return
        if fmt not in ("docx", "pdf"):
            return

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
            stype = ServiceType(service_type_value)
            svc = get_service(stype)
            service_name = svc.name
        except (ValueError, KeyError):
            service_name = service_type_value

        result_text = order["output_text"]
        order_date = order.get("completed_at") or order.get("created_at", "")

        import os as _os
        try:
            if fmt == "docx":
                filepath = await document_generator.generate_docx(
                    order_id, service_name, result_text, order_date
                )
            else:
                filepath = await document_generator.generate_pdf(
                    order_id, service_name, result_text, order_date
                )

            with open(filepath, "rb") as f:
                await context.bot.send_document(
                    chat_id=user.id,
                    document=f,
                    filename=f"order_{order_id}.{fmt}",
                )

            # Удаляем временный файл после отправки
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

    # Строим Application
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_SERVICE: [CallbackQueryHandler(select_service)],
            ENTER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_text)],
            SELECT_URGENCY: [CallbackQueryHandler(select_urgency)],
            CONFIRM_ORDER: [CallbackQueryHandler(confirm_order)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(
        CallbackQueryHandler(handle_rating, pattern=r"^rate:\d+:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(handle_download, pattern=r"^download:\d+:(docx|pdf)$")
    )

    return application

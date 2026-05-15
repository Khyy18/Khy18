"""Апселл-агент: предложение дополнительных услуг после заказа."""

import logging
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
import database
from utils import _card, format_number

logger = logging.getLogger(__name__)

# Lazy OpenAI client
_openai_client = None


def _get_openai_client():
    """Получить или создать singleton AsyncOpenAI клиент."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


# Дополнительные услуги (аддоны) для каждого типа сервиса
ADDONS: Dict[str, List[dict]] = {
    "copywriting": [
        {"name": "SEO-оптимизация", "description": "Добавить ключевые слова и мета-описание", "price": 50.0},
        {"name": "Заголовки A/B", "description": "3 варианта заголовка для тестирования", "price": 30.0},
        {"name": "Адаптация для соцсетей", "description": "Версии для Instagram, VK, Telegram", "price": 80.0},
    ],
    "rewrite": [
        {"name": "Проверка уникальности", "description": "Отчёт о процентах уникальности", "price": 30.0},
        {"name": "Стилистическая правка", "description": "Улучшение стиля и читабельности", "price": 50.0},
    ],
    "seo": [
        {"name": "Кластеризация запросов", "description": "Группировка ключевых слов по интенту", "price": 60.0},
        {"name": "Мета-теги", "description": "Title + Description для страницы", "price": 40.0},
    ],
    "translation": [
        {"name": "Второй язык", "description": "Перевод на дополнительный язык", "price": 80.0},
        {"name": "Глоссарий терминов", "description": "Список переведённых терминов", "price": 40.0},
    ],
    "summary": [
        {"name": "Инфографика-текст", "description": "Текст для визуальной инфографики", "price": 50.0},
        {"name": "Тезисы для презентации", "description": "Ключевые пункты для слайдов", "price": 60.0},
    ],
    "smm": [
        {"name": "Хештеги", "description": "Набор релевантных хештегов", "price": 30.0},
        {"name": "Контент-план на неделю", "description": "7 идей для постов", "price": 70.0},
    ],
}


async def generate_upsell(service_type: str, result_text: str) -> Optional[str]:
    """
    Генерировать предложение апселла на основе типа услуги и результата.
    """
    addons = ADDONS.get(service_type, [])
    if not addons:
        return None

    addon_names = ", ".join(a["name"] for a in addons)
    try:
        client = _get_openai_client()
        response = await client.chat.completions.create(
            model=config.DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты продавец-консультант. Предложи дополнительную услугу "
                        "клиенту после выполнения заказа. Кратко, 1-2 предложения."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Услуга: {service_type}. "
                        f"Доступные аддоны: {addon_names}. "
                        f"Начало результата: {result_text[:200]}. "
                        "Предложи подходящий аддон."
                    ),
                },
            ],
            max_tokens=150,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error("Ошибка генерации upsell: %s", e)
        return None


def get_upsell_keyboard(order_id: int, service_type: str) -> Optional[InlineKeyboardMarkup]:
    """Создать клавиатуру с кнопками апселла."""
    addons = ADDONS.get(service_type, [])
    if not addons:
        return None

    keyboard = []
    for idx, addon in enumerate(addons):
        keyboard.append([
            InlineKeyboardButton(
                f"{addon['name']} - {format_number(addon['price'])} \u20bd",
                callback_data=f"upsell:{order_id}:{idx}",
            )
        ])
    keyboard.append([
        InlineKeyboardButton("\u274c Нет, спасибо", callback_data="upsell_skip"),
    ])
    return InlineKeyboardMarkup(keyboard)


async def handle_upsell_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка покупки аддона."""
    query = update.callback_query
    await query.answer()

    if query.data == "upsell_skip":
        await query.edit_message_text(
            "\u2705 Спасибо за заказ! Нажмите /start для нового.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Парсим callback_data: upsell:{order_id}:{addon_index}
    parts = query.data.split(":")
    if len(parts) != 3:
        return

    try:
        order_id = int(parts[1])
        addon_idx = int(parts[2])
    except (ValueError, IndexError):
        return

    user = update.effective_user

    # Получаем заказ
    order = await database.get_order_by_id(order_id)
    if not order or order.get("client_id") != user.id:
        await query.edit_message_text(
            "\u274c Заказ не найден.",
            parse_mode=ParseMode.HTML,
        )
        return

    service_type = order["service_type"]
    addons = ADDONS.get(service_type, [])

    if addon_idx < 0 or addon_idx >= len(addons):
        await query.edit_message_text(
            "\u274c Аддон не найден.",
            parse_mode=ParseMode.HTML,
        )
        return

    addon = addons[addon_idx]
    price = addon["price"]

    # Проверяем баланс
    balance = await database.get_client_balance(user.id)
    if balance < price:
        body = [
            f"<b>Аддон:</b> {addon['name']}",
            f"<b>Стоимость:</b> {format_number(price)} \u20bd",
            f"<b>Баланс:</b> {format_number(balance)} \u20bd",
            "",
            "Недостаточно средств. Пополните баланс.",
        ]
        text = _card("Недостаточно средств", "\U0001f6ab", body)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return

    # Списываем средства
    new_balance = balance - price
    await database.update_balance(user.id, new_balance)

    body = [
        f"<b>Аддон:</b> {addon['name']}",
        f"<b>Описание:</b> {addon['description']}",
        f"<b>Списано:</b> {format_number(price)} \u20bd",
        "",
        "Результат будет готов в течение минуты.",
    ]
    text = _card("Аддон оформлен", "\u2705", body)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    logger.info(
        "Upsell purchase: user=%d, order=%d, addon=%s, price=%.2f",
        user.id, order_id, addon["name"], price,
    )

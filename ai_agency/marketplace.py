"""Маркетплейс шаблонов: покупка и автогенерация шаблонов."""

import logging
from typing import List, Optional

import aiosqlite
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


# Категории шаблонов
CATEGORIES = {
    "social_posts": "Посты для соцсетей",
    "email_templates": "Email-шаблоны",
    "product_descriptions": "Описания товаров",
    "proposals": "Коммерческие предложения",
}


async def init_marketplace_tables() -> None:
    """Создать таблицы маркетплейса."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                preview TEXT NOT NULL,
                full_text TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 50.0,
                sales_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS template_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                template_id INTEGER NOT NULL,
                purchased_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id),
                FOREIGN KEY (template_id) REFERENCES templates(id)
            )
        """)
        await db.commit()


def get_categories() -> List[dict]:
    """Получить список категорий шаблонов."""
    return [{"key": k, "name": v} for k, v in CATEGORIES.items()]


async def get_templates_by_category(category: str, limit: int = 10) -> List[dict]:
    """Получить шаблоны по категории."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM templates WHERE category = ?
               ORDER BY sales_count DESC LIMIT ?""",
            (category, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_template_by_id(template_id: int) -> Optional[dict]:
    """Получить шаблон по ID."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM templates WHERE id = ?", (template_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def purchase_template(client_id: int, template_id: int) -> bool:
    """Купить шаблон. Возвращает True при успехе."""
    template = await get_template_by_id(template_id)
    if not template:
        return False

    price = template["price"]

    # Atomic balance deduction to prevent race conditions
    deducted = await database.atomic_deduct_balance(client_id, price)
    if not deducted:
        return False

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Записываем покупку
        await db.execute(
            "INSERT INTO template_purchases (client_id, template_id) VALUES (?, ?)",
            (client_id, template_id),
        )
        # Увеличиваем счётчик продаж
        await db.execute(
            "UPDATE templates SET sales_count = sales_count + 1 WHERE id = ?",
            (template_id,),
        )
        await db.commit()

    logger.info("Template purchase: client=%d, template=%d, price=%.2f", client_id, template_id, price)
    return True


async def generate_new_templates(category: str, count: int = 3) -> List[int]:
    """Сгенерировать новые шаблоны для категории. Возвращает список ID."""
    category_name = CATEGORIES.get(category, category)
    created_ids = []

    try:
        client = _get_openai_client()
        for _ in range(count):
            response = await client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты генератор шаблонов текстов. Создай готовый шаблон "
                            "который пользователь может адаптировать под свои нужды."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Создай шаблон для категории '{category_name}'. "
                            "Формат ответа JSON: "
                            '{"title": "Название", "text": "Полный текст шаблона"}'
                        ),
                    },
                ],
                max_tokens=800,
                temperature=0.8,
            )
            content = response.choices[0].message.content

            # Парсим JSON из ответа
            import json
            try:
                data = json.loads(content)
                title = data.get("title", f"Шаблон {category_name}")
                full_text = data.get("text", content)
            except (json.JSONDecodeError, TypeError):
                title = f"Шаблон {category_name}"
                full_text = content

            preview = full_text[:150] + "..."

            # Сохраняем в БД
            async with aiosqlite.connect(config.DATABASE_PATH) as db:
                cursor = await db.execute(
                    """INSERT INTO templates (category, title, preview, full_text, price)
                       VALUES (?, ?, ?, ?, ?)""",
                    (category, title, preview, full_text, 50.0),
                )
                await db.commit()
                created_ids.append(cursor.lastrowid)

    except Exception as e:
        logger.error("Ошибка генерации шаблонов: %s", e)

    return created_ids


# --- Bot UI functions ---

async def show_marketplace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать главную страницу маркетплейса."""
    query = update.callback_query
    if query:
        await query.answer()

    body = [
        "Готовые шаблоны текстов для любых задач.",
        "Выберите категорию:",
    ]
    text = _card("Маркетплейс шаблонов", "\U0001f6cd", body)

    keyboard = []
    for key, name in CATEGORIES.items():
        keyboard.append([
            InlineKeyboardButton(name, callback_data=f"mkt_cat:{key}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать шаблоны в категории."""
    query = update.callback_query
    await query.answer()

    category = query.data.replace("mkt_cat:", "")
    category_name = CATEGORIES.get(category, category)

    templates = await get_templates_by_category(category, limit=5)

    if not templates:
        body = ["Пока нет шаблонов в этой категории.", "Загляните позже!"]
        text = _card(category_name, "\U0001f4c4", body)
        keyboard = [[InlineKeyboardButton("\u2b05 Назад", callback_data="marketplace")]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
        return

    body = [f"<b>{category_name}</b>", ""]
    keyboard = []
    for t in templates:
        body.append(f"\u2022 {t['title']} - {format_number(t['price'])} \u20bd")
        keyboard.append([
            InlineKeyboardButton(
                t["title"][:30],
                callback_data=f"mkt_tpl:{t['id']}",
            )
        ])

    keyboard.append([InlineKeyboardButton("\u2b05 Назад", callback_data="marketplace")])
    text = _card("Шаблоны", "\U0001f4c4", body)
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )


async def show_template_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать превью шаблона с кнопкой покупки."""
    query = update.callback_query
    await query.answer()

    tpl_id_str = query.data.replace("mkt_tpl:", "")
    try:
        tpl_id = int(tpl_id_str)
    except ValueError:
        return

    template = await get_template_by_id(tpl_id)
    if not template:
        await query.edit_message_text("\u274c Шаблон не найден.", parse_mode=ParseMode.HTML)
        return

    body = [
        f"<b>{template['title']}</b>",
        f"<b>Категория:</b> {CATEGORIES.get(template['category'], template['category'])}",
        f"<b>Цена:</b> {format_number(template['price'])} \u20bd",
        f"<b>Продаж:</b> {template['sales_count']}",
        "",
        "<b>Превью:</b>",
        f"<i>{template['preview']}</i>",
    ]
    text = _card("Шаблон", "\U0001f4c4", body)

    keyboard = [
        [InlineKeyboardButton(
            f"\U0001f6d2 Купить за {format_number(template['price'])} \u20bd",
            callback_data=f"mkt_buy:{tpl_id}",
        )],
        [InlineKeyboardButton("\u2b05 Назад", callback_data=f"mkt_cat:{template['category']}")],
    ]

    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
    )


async def handle_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка покупки шаблона."""
    query = update.callback_query
    await query.answer()

    tpl_id_str = query.data.replace("mkt_buy:", "")
    try:
        tpl_id = int(tpl_id_str)
    except ValueError:
        return

    user = update.effective_user
    success = await purchase_template(user.id, tpl_id)

    if success:
        template = await get_template_by_id(tpl_id)
        if template:
            body = [
                f"<b>{template['title']}</b>",
                "",
                template["full_text"][:2000],
            ]
            text = _card("Покупка завершена", "\u2705", body)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(
                "\u2705 Покупка завершена!", parse_mode=ParseMode.HTML
            )
    else:
        body = ["Недостаточно средств или шаблон не найден.", "Пополните баланс через /start."]
        text = _card("Ошибка покупки", "\u274c", body)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

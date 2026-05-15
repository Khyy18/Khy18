"""Модуль автоматического онбординга новых пользователей AI-агентства."""

import logging
from datetime import datetime
from typing import Optional

import aiosqlite
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import config
from utils import _card, format_number
from services import SERVICES

logger = logging.getLogger(__name__)

# Шаги онбординга
ONBOARDING_STEPS = [
    "services_carousel",
    "free_trial",
    "how_it_works",
    "bonus_offer",
]


async def _track_onboarding_event(
    telegram_id: int, step: str, action: str = "view"
) -> None:
    """Записать событие онбординга в БД."""
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                """INSERT INTO onboarding_events
                   (telegram_id, step, action, created_at)
                   VALUES (?, ?, ?, ?)""",
                (telegram_id, step, action, datetime.utcnow().isoformat()),
            )
            await db.commit()
    except Exception as e:
        logger.debug("Ошибка записи onboarding event: %s", e)


async def _step_services_carousel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Шаг 1: карусель услуг с примерами."""
    body_lines = [
        "Я могу создать для вас:",
        "",
    ]
    for stype, sdef in list(SERVICES.items())[:5]:
        body_lines.append(f"  \u2022 <b>{sdef.name}</b> - {sdef.description}")

    body_lines.extend([
        "",
        f"...и ещё {max(0, len(SERVICES) - 5)} услуг!",
    ])

    text = _card("Что я умею", "\U0001f4cb", body_lines)

    keyboard = [
        [InlineKeyboardButton("Далее \u27a1", callback_data="onboard_next:1")],
        [InlineKeyboardButton("Пропустить \u23ed", callback_data="onboard_skip")],
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def _step_free_trial(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Шаг 2: предложение бесплатного пробного заказа."""
    body_lines = [
        "Первый заказ - <b>бесплатно</b>!",
        "",
        "Выберите любую услугу и убедитесь в качестве.",
        "Никаких обязательств.",
    ]

    text = _card("Попробуйте бесплатно", "\U0001f381", body_lines)

    keyboard = [
        [InlineKeyboardButton("Далее \u27a1", callback_data="onboard_next:2")],
        [InlineKeyboardButton("Пропустить \u23ed", callback_data="onboard_skip")],
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )


async def _step_how_it_works(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Шаг 3: мини-демо с объяснением процесса."""
    body_lines = [
        "1\u20e3 Выбираете услугу",
        "2\u20e3 Отправляете текст задания",
        "3\u20e3 AI-команда обрабатывает (Writer \u2192 Editor \u2192 QA)",
        "4\u20e3 Получаете результат за 1-3 минуты",
        "",
        "<i>Пример: \"Напиши пост для Instagram о кофейне\"</i>",
        "<i>\u2192 Готовый продающий текст с хештегами</i>",
    ]

    text = _card("Как это работает", "\u2699\ufe0f", body_lines)

    keyboard = [
        [InlineKeyboardButton("Далее \u27a1", callback_data="onboard_next:3")],
        [InlineKeyboardButton("Пропустить \u23ed", callback_data="onboard_skip")],
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )


async def _step_bonus_offer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Шаг 4: бонус 20% на второй заказ."""
    body_lines = [
        "\U0001f389 Специально для вас:",
        "",
        "<b>Скидка 20% на второй заказ!</b>",
        "",
        "Промокод активируется автоматически.",
        "Действует 7 дней с момента регистрации.",
    ]

    text = _card("Ваш бонус", "\U0001f4b5", body_lines)

    keyboard = [
        [InlineKeyboardButton("\U0001f680 Начать работу!", callback_data="onboard_finish")],
    ]

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )


STEP_HANDLERS = [
    _step_services_carousel,
    _step_free_trial,
    _step_how_it_works,
    _step_bonus_offer,
]


async def start_onboarding(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Запустить онбординг-тур для нового пользователя.

    Возвращает номер шага ConversationHandler (SELECT_SERVICE=0).
    """
    user = update.effective_user
    context.user_data["onboarding_step"] = 0

    await _track_onboarding_event(user.id, ONBOARDING_STEPS[0], "view")
    await _step_services_carousel(update, context)

    return 0  # SELECT_SERVICE state


async def handle_onboarding_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
    """
    Обработать callback от кнопок онбординга.

    Возвращает None если callback не относится к онбордингу.
    """
    query = update.callback_query
    data = query.data

    if not data or not data.startswith("onboard_"):
        return None

    await query.answer()
    user = update.effective_user

    if data == "onboard_skip":
        current_step = context.user_data.get("onboarding_step", 0)
        await _track_onboarding_event(
            user.id, ONBOARDING_STEPS[min(current_step, len(ONBOARDING_STEPS) - 1)], "skip"
        )
        context.user_data.pop("onboarding_step", None)
        return 0  # Return to SELECT_SERVICE

    if data == "onboard_finish":
        await _track_onboarding_event(user.id, "completed", "finish")
        context.user_data.pop("onboarding_step", None)
        return 0  # Return to SELECT_SERVICE

    if data.startswith("onboard_next:"):
        try:
            next_step = int(data.split(":")[1])
        except (ValueError, IndexError):
            return 0

        context.user_data["onboarding_step"] = next_step

        if next_step < len(STEP_HANDLERS):
            await _track_onboarding_event(
                user.id, ONBOARDING_STEPS[next_step], "view"
            )
            await STEP_HANDLERS[next_step](update, context)
        else:
            context.user_data.pop("onboarding_step", None)

        return 0

    return None


async def get_drop_off_stats() -> dict:
    """Получить статистику по шагам, где пользователи уходят."""
    stats = {}
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            for step in ONBOARDING_STEPS:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM onboarding_events WHERE step = ? AND action = 'view'",
                    (step,),
                )
                row = await cursor.fetchone()
                views = row[0] if row else 0

                cursor = await db.execute(
                    "SELECT COUNT(*) FROM onboarding_events WHERE step = ? AND action = 'skip'",
                    (step,),
                )
                row = await cursor.fetchone()
                skips = row[0] if row else 0

                stats[step] = {"views": views, "skips": skips}
    except Exception as e:
        logger.debug("Ошибка получения drop-off stats: %s", e)

    return stats

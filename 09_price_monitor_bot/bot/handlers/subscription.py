"""Обработчики для управления подпиской (VIP / Free)."""

from datetime import datetime

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.queries import get_user, update_user_vip
from bot.ui.cards import card, progress_bar, status_indicator

router = Router()


@router.callback_query(lambda c: c.data == "sub:info")
async def cb_sub_info(callback: CallbackQuery) -> None:
    """Показать текущий план подписки."""
    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    is_vip = bool(user.get("is_vip"))

    if is_vip:
        indicator = status_indicator("high")
        # Рассчитываем оставшиеся дни по vip_expires_at
        vip_expires_at = user.get("vip_expires_at")
        if vip_expires_at:
            try:
                expires_dt = datetime.fromisoformat(vip_expires_at)
                days_left = max(0, (expires_dt - datetime.now()).days)
            except (ValueError, TypeError):
                days_left = 0
        else:
            days_left = 0

        bar = progress_bar(days_left, 30)
        lines = [
            f"<b>Статус:</b> {indicator} VIP",
            "",
            f"<b>Осталось дней:</b> {days_left}",
            f"{bar} {days_left}/30",
            "",
            "\u2022 Мгновенные уведомления об алертах",
            "\u2022 Приоритетная обработка",
            "\u2022 Расширенная аналитика",
            "\u2022 Селлер-режим без ограничений",
        ]
    else:
        indicator = status_indicator("medium")
        lines = [
            f"<b>Статус:</b> {indicator} Бесплатный план",
            "",
            "\u2022 Уведомления с задержкой 30 мин",
            "\u2022 До 5 активных алертов",
            "\u2022 Базовая аналитика",
            "",
            "Обновите до <b>VIP</b> для мгновенных алертов! \u2b06\ufe0f",
        ]

    text = card(title="Подписка", emoji="\u2b50", body_lines=lines)

    buttons = []
    if is_vip:
        buttons.append([InlineKeyboardButton(text="\u274c Отменить VIP", callback_data="sub:downgrade")])
    else:
        buttons.append([InlineKeyboardButton(text="\U0001f680 Обновить до VIP", callback_data="sub:upgrade")])
    buttons.append([InlineKeyboardButton(text="\u2b05 Меню", callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "sub:upgrade")
async def cb_sub_upgrade(callback: CallbackQuery) -> None:
    """Показать информацию об обновлении до VIP."""
    text = card(
        title="VIP-подписка",
        emoji="\U0001f680",
        body_lines=[
            "<b>Преимущества VIP:</b>",
            "",
            "\u2022 Мгновенные алерты (без задержки)",
            "\u2022 Неограниченное кол-во алертов",
            "\u2022 Селлер-режим: до 50 мониторов",
            "\u2022 Приоритетная поддержка",
            "",
            "\U0001f4b3 <i>Интеграция оплаты в разработке.</i>",
            "Для активации VIP свяжитесь с администратором.",
        ],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2b05 Назад", callback_data="sub:info")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "sub:downgrade")
async def cb_sub_downgrade(callback: CallbackQuery) -> None:
    """Подтверждение отмены VIP."""
    text = card(
        title="Отмена VIP",
        emoji="\u26a0\ufe0f",
        body_lines=[
            "Вы уверены, что хотите отменить VIP?",
            "",
            "Вы потеряете:",
            "\u2022 Мгновенные уведомления",
            "\u2022 Расширенные лимиты",
            "\u2022 Приоритетную поддержку",
        ],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2705 Да, отменить", callback_data="sub:downgrade:confirm"),
            InlineKeyboardButton(text="\u274c Нет", callback_data="sub:info"),
        ],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "sub:downgrade:confirm")
async def cb_sub_downgrade_confirm(callback: CallbackQuery) -> None:
    """Выполнить отмену VIP."""
    telegram_id = callback.from_user.id
    await update_user_vip(telegram_id, is_vip=False)
    await callback.answer("\u2705 VIP отменен")
    # Показать обновленную информацию
    await cb_sub_info(callback)

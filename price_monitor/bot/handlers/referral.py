"""Обработчики для реферальной программы."""

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.queries import get_referral_count, get_user, get_top_referrers
from bot.ui.cards import card, progress_bar

router = Router()


@router.callback_query(lambda c: c.data == "ref:info")
async def cb_ref_info(callback: CallbackQuery) -> None:
    """Показать реферальную информацию пользователя."""
    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    referral_code = user.get("referral_code", "")
    count = await get_referral_count(referral_code)

    # Прогресс к следующей награде (каждые 5 приглашений)
    next_reward = 5
    bar = progress_bar(count % next_reward, next_reward)

    lines = [
        f"\U0001f517 <b>Ваша ссылка:</b>",
        f"<code>https://t.me/price_monitor_bot?start=ref_{referral_code}</code>",
        "",
        f"\U0001f465 <b>Приглашено друзей:</b> {count}",
        f"{bar} {count % next_reward}/{next_reward} до награды",
        "",
        "\U0001f381 <b>Правила:</b>",
        "\u2022 Пригласите друга \u2192 7 дней VIP бесплатно",
        "\u2022 Каждые 5 приглашений \u2192 бонус 30 дней VIP",
    ]

    text = card(title="Реферальная программа", emoji="\U0001f91d", body_lines=lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f3c6 Топ рефереров", callback_data="ref:top")],
        [InlineKeyboardButton(text="\u2b05 Меню", callback_data="menu:main")],
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "ref:top")
async def cb_ref_top(callback: CallbackQuery) -> None:
    """Показать топ-5 рефереров."""
    top = await get_top_referrers(limit=5)

    if not top:
        lines = ["Пока нет данных о рефералах."]
    else:
        lines = []
        medals = ["\U0001f947", "\U0001f948", "\U0001f949", "4\ufe0f\u20e3", "5\ufe0f\u20e3"]
        for i, entry in enumerate(top):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            name = entry.get("username") or f"User #{entry['telegram_id']}"
            lines.append(f"{medal} {name} \u2014 {entry['count']} приглашений")

    text = card(title="Топ рефереров", emoji="\U0001f3c6", body_lines=lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2b05 Назад", callback_data="ref:info")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()

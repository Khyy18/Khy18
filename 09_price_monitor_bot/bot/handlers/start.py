"""Обработчик /start и главное меню."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.queries import add_user, get_user, get_user_by_referral_code, generate_referral_code
from bot.ui.cards import card

router = Router()


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\U0001f514 Мои алерты", callback_data="alerts:list"),
            InlineKeyboardButton(text="\u2b50 Подписка", callback_data="sub:info"),
        ],
        [
            InlineKeyboardButton(text="\U0001f4ca Селлер-режим", callback_data="seller:menu"),
            InlineKeyboardButton(text="\U0001f465 Рефералы", callback_data="ref:info"),
        ],
        [
            InlineKeyboardButton(text="\u2753 Помощь", callback_data="menu:help"),
        ],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработка команды /start с поддержкой deeplink реферальных кодов."""
    telegram_id = message.from_user.id  # type: ignore[union-attr]
    username = message.from_user.username  # type: ignore[union-attr]

    # Проверяем deeplink (например /start ref_abc12345)
    referred_by: str | None = None
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) > 1 and args[1].startswith("ref_"):
        referred_by = args[1][4:]  # убираем префикс ref_

    user = await get_user(telegram_id)
    if user is None:
        # Регистрация нового пользователя
        referral_code = generate_referral_code()
        await add_user(
            telegram_id=telegram_id,
            username=username,
            referral_code=referral_code,
            referred_by=referred_by,
        )
    else:
        referred_by = None  # уже зарегистрирован, не кредитим повторно

    welcome_text = card(
        title="Price Monitor Bot",
        emoji="\U0001f4b0",
        body_lines=[
            "Мониторинг цен на Wildberries и Ozon.",
            "",
            "\u2022 Персональные алерты по ключевым словам",
            "\u2022 Мгновенные уведомления о скидках (VIP)",
            "\u2022 Режим селлера: следите за конкурентами",
            "\u2022 Реферальная программа: приглашай друзей",
            "",
            "Выберите действие в меню ниже \u2b07\ufe0f",
        ],
    )

    await message.answer(welcome_text, reply_markup=_main_menu_keyboard(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == "menu:help")
async def cb_help(callback: CallbackQuery) -> None:
    """Показать помощь по использованию бота."""
    help_text = card(
        title="Помощь",
        emoji="\U0001f4d6",
        body_lines=[
            "<b>Как пользоваться ботом:</b>",
            "",
            "1\ufe0f\u20e3 <b>Алерты</b> \u2014 добавьте ключевое слово и макс. цену.",
            "   Бот уведомит, когда товар подешевеет.",
            "",
            "2\ufe0f\u20e3 <b>Подписка</b> \u2014 VIP получает алерты мгновенно,",
            "   бесплатный план \u2014 с задержкой 30 мин.",
            "",
            "3\ufe0f\u20e3 <b>Селлер-режим</b> \u2014 отслеживайте цены конкурентов",
            "   и получайте аналитику.",
            "",
            "4\ufe0f\u20e3 <b>Рефералы</b> \u2014 пригласите друга и получите",
            "   7 дней VIP бесплатно.",
        ],
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2b05 Назад в меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(help_text, reply_markup=back_kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    """Возврат в главное меню."""
    welcome_text = card(
        title="Price Monitor Bot",
        emoji="\U0001f4b0",
        body_lines=[
            "Мониторинг цен на Wildberries и Ozon.",
            "",
            "Выберите действие в меню ниже \u2b07\ufe0f",
        ],
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        welcome_text, reply_markup=_main_menu_keyboard(), parse_mode="HTML"
    )
    await callback.answer()

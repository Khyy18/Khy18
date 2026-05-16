"""Обработчики для режима селлера (мониторинг конкурентов)."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.queries import add_seller_monitor, delete_seller_monitor, get_seller_monitor_by_id, get_user, get_user_monitors
from bot.ui.cards import card, sparkline

router = Router()


class AddMonitorStates(StatesGroup):
    """FSM-состояния для добавления мониторинга конкурента."""

    waiting_url = State()
    waiting_marketplace = State()


@router.callback_query(lambda c: c.data == "seller:menu")
async def cb_seller_menu(callback: CallbackQuery) -> None:
    """Главное меню режима селлера."""
    text = card(
        title="Селлер-режим",
        emoji="\U0001f4ca",
        body_lines=[
            "Отслеживайте цены конкурентов на маркетплейсах.",
            "",
            "\u2022 Добавьте товары конкурентов для мониторинга",
            "\u2022 Получайте уведомления об изменении цен",
            "\u2022 Анализируйте тренды с помощью графиков",
            "",
            "\u26a0\ufe0f <i>Расширенный тариф: до 10 мониторов (Free),",
            "до 50 мониторов (VIP).</i>",
        ],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4cb Мои мониторы", callback_data="seller:list")],
        [InlineKeyboardButton(text="\u2795 Добавить конкурента", callback_data="seller:add")],
        [InlineKeyboardButton(text="\u2b05 Меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "seller:list")
async def cb_seller_list(callback: CallbackQuery) -> None:
    """Показать список мониторов конкурентов."""
    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    monitors = await get_user_monitors(user["id"])

    if not monitors:
        text = card(
            title="Мои мониторы",
            emoji="\U0001f4cb",
            body_lines=[
                "У вас пока нет активных мониторов.",
                "",
                "Нажмите <b>Добавить конкурента</b>, чтобы начать.",
            ],
        )
    else:
        lines: list[str] = []
        for m in monitors:
            # Спарклайн для демонстрации (реальные данные будут из price_history)
            trend = sparkline([100, 95, 98, 90, 87, 92, 85])
            mp_label = m["marketplace"].upper()
            lines.append(f"\U0001f6d2 <b>{mp_label}</b>: {m['competitor_url'][:40]}...")
            lines.append(f"   Тренд: {trend}")
            lines.append("")
        text = card(title="Мои мониторы", emoji="\U0001f4cb", body_lines=lines)

    buttons = [[InlineKeyboardButton(text="\u2795 Добавить", callback_data="seller:add")]]
    for m in monitors:
        buttons.append([
            InlineKeyboardButton(
                text=f"\u274c {m['marketplace'].upper()} | {m['competitor_url'][:25]}",
                callback_data=f"seller:delete:{m['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="\u2b05 Селлер-меню", callback_data="seller:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "seller:add")
async def cb_seller_add(callback: CallbackQuery, state: FSMContext) -> None:
    """Начать FSM добавления мониторинга: запросить URL."""
    await state.set_state(AddMonitorStates.waiting_url)
    text = card(
        title="Добавить конкурента",
        emoji="\U0001f50d",
        body_lines=[
            "Введите URL товара конкурента или артикул:",
            "",
            "<i>Пример: https://www.wildberries.ru/catalog/12345</i>",
            "<i>или просто артикул: 12345</i>",
        ],
    )
    await callback.message.edit_text(text, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.message(AddMonitorStates.waiting_url)
async def msg_monitor_url(message: Message, state: FSMContext) -> None:
    """Получить URL/артикул, запросить маркетплейс."""
    url = (message.text or "").strip()
    if not url:
        await message.answer("Введите URL или артикул товара:")
        return
    await state.update_data(url=url)
    await state.set_state(AddMonitorStates.waiting_marketplace)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Wildberries", callback_data="seller:mp:wb"),
            InlineKeyboardButton(text="Ozon", callback_data="seller:mp:ozon"),
        ],
    ])
    await message.answer(
        "\U0001f3ea Выберите маркетплейс:", reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data and c.data.startswith("seller:mp:"))
async def cb_seller_marketplace(callback: CallbackQuery, state: FSMContext) -> None:
    """Получить маркетплейс, сохранить монитор в БД."""
    current_state = await state.get_state()
    if current_state != AddMonitorStates.waiting_marketplace.state:
        await callback.answer("Сессия истекла, начните заново", show_alert=True)
        return

    marketplace = callback.data.split(":")[2]  # type: ignore[union-attr]
    data = await state.get_data()
    url = data["url"]

    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Ошибка: нажмите /start", show_alert=True)
        await state.clear()
        return

    await add_seller_monitor(user_id=user["id"], competitor_url=url, marketplace=marketplace)
    await state.clear()

    mp_label = "Wildberries" if marketplace == "wb" else "Ozon"
    confirm_text = card(
        title="Монитор добавлен!",
        emoji="\u2705",
        body_lines=[
            f"<b>Маркетплейс:</b> {mp_label}",
            f"<b>URL/Артикул:</b> {url}",
            "",
            "Бот будет отслеживать изменения цены.",
        ],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4cb Мои мониторы", callback_data="seller:list")],
        [InlineKeyboardButton(text="\u2b05 Меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(confirm_text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("seller:delete:"))
async def cb_seller_delete(callback: CallbackQuery) -> None:
    """Удалить конкретный монитор (с проверкой владельца)."""
    monitor_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]

    # Проверка принадлежности монитора текущему пользователю
    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    monitor = await get_seller_monitor_by_id(monitor_id)
    if monitor is None:
        await callback.answer("\u274c Монитор не найден", show_alert=True)
        return

    if monitor["user_id"] != user["id"]:
        await callback.answer("\u274c Нет доступа к этому монитору", show_alert=True)
        return

    await delete_seller_monitor(monitor_id)
    await callback.answer("\u2705 Монитор удален")
    # Показать обновленный список
    await cb_seller_list(callback)

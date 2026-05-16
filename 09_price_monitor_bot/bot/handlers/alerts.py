"""Обработчики для управления персональными алертами."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.db.queries import add_alert, delete_alert, get_alert_by_id, get_user, get_user_alerts
from bot.ui.cards import card, format_number, status_indicator

router = Router()


class AddAlertStates(StatesGroup):
    """FSM-состояния для добавления алерта."""

    waiting_keyword = State()
    waiting_price = State()


@router.callback_query(lambda c: c.data == "alerts:list")
async def cb_alerts_list(callback: CallbackQuery) -> None:
    """Показать список алертов пользователя."""
    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    alerts = await get_user_alerts(user["id"])

    if not alerts:
        text = card(
            title="Мои алерты",
            emoji="\U0001f514",
            body_lines=[
                "У вас пока нет активных алертов.",
                "",
                "Нажмите <b>Добавить алерт</b>, чтобы создать первый.",
            ],
        )
    else:
        lines: list[str] = []
        for a in alerts:
            indicator = status_indicator("high")
            price_str = format_number(a["max_price"]) if a["max_price"] else "без лимита"
            lines.append(f"{indicator} <b>{a['keyword']}</b> \u2014 до {price_str} \u20bd")
        text = card(title="Мои алерты", emoji="\U0001f514", body_lines=lines)

    buttons = [[InlineKeyboardButton(text="\u2795 Добавить алерт", callback_data="alerts:add")]]
    # Кнопки удаления для каждого алерта
    for a in alerts:
        buttons.append([
            InlineKeyboardButton(
                text=f"\u274c {a['keyword']}", callback_data=f"alerts:delete:{a['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="\u2b05 Меню", callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(lambda c: c.data == "alerts:add")
async def cb_alerts_add(callback: CallbackQuery, state: FSMContext) -> None:
    """Начать FSM добавления алерта: запросить ключевое слово."""
    await state.set_state(AddAlertStates.waiting_keyword)
    text = card(
        title="Новый алерт",
        emoji="\u270f\ufe0f",
        body_lines=[
            "Введите ключевое слово или название товара,",
            "по которому хотите отслеживать цену:",
        ],
    )
    await callback.message.edit_text(text, parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()


@router.message(AddAlertStates.waiting_keyword)
async def msg_alert_keyword(message: Message, state: FSMContext) -> None:
    """Получить ключевое слово, запросить максимальную цену."""
    keyword = (message.text or "").strip()
    if not keyword:
        await message.answer("Введите непустое ключевое слово:")
        return
    await state.update_data(keyword=keyword)
    await state.set_state(AddAlertStates.waiting_price)
    await message.answer(
        f"\U0001f4b0 Введите максимальную цену в рублях для <b>{keyword}</b>\n"
        "(или отправьте 0, если без лимита):",
        parse_mode="HTML",
    )


@router.message(AddAlertStates.waiting_price)
async def msg_alert_price(message: Message, state: FSMContext) -> None:
    """Получить цену, сохранить алерт в БД."""
    raw = (message.text or "").strip().replace(" ", "").replace("\u202f", "")
    try:
        price = float(raw)
    except ValueError:
        await message.answer("\u274c Введите число (цену в рублях):")
        return

    data = await state.get_data()
    keyword = data["keyword"]
    max_price = price if price > 0 else None

    telegram_id = message.from_user.id  # type: ignore[union-attr]
    user = await get_user(telegram_id)
    if user is None:
        await message.answer("Ошибка: пользователь не найден. Нажмите /start")
        await state.clear()
        return

    await add_alert(user_id=user["id"], keyword=keyword, max_price=max_price)
    await state.clear()

    price_display = format_number(max_price) + " \u20bd" if max_price else "без лимита"
    confirm_text = card(
        title="Алерт создан!",
        emoji="\u2705",
        body_lines=[
            f"<b>Ключевое слово:</b> {keyword}",
            f"<b>Макс. цена:</b> {price_display}",
            "",
            "Вы получите уведомление, когда товар появится по этой цене.",
        ],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f514 Мои алерты", callback_data="alerts:list")],
        [InlineKeyboardButton(text="\u2b05 Меню", callback_data="menu:main")],
    ])
    await message.answer(confirm_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith("alerts:delete:"))
async def cb_alerts_delete(callback: CallbackQuery) -> None:
    """Удалить конкретный алерт (с проверкой владельца)."""
    alert_id = int(callback.data.split(":")[2])  # type: ignore[union-attr]

    # Проверка принадлежности алерта текущему пользователю
    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    if user is None:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return

    alert = await get_alert_by_id(alert_id)
    if alert is None:
        await callback.answer("\u274c Алерт не найден", show_alert=True)
        return

    if alert["user_id"] != user["id"]:
        await callback.answer("\u274c Нет доступа к этому алерту", show_alert=True)
        return

    await delete_alert(alert_id)
    await callback.answer("\u2705 Алерт удален")
    # Показать обновленный список
    await cb_alerts_list(callback)

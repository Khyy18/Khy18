"""AI Office Bot - unified control panel via Telegram inline buttons."""

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
import httpx
import logging
import datetime

logger = logging.getLogger(__name__)

router = Router()

SERVICES = {
    "price_monitor": "http://localhost:8000",
    "outbound": "http://localhost:8001",
    "text_agency": "http://localhost:8002",
}

ADMIN_ID = 0


# ─── Keyboards ───────────────────────────────────────────────────────────────

def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Дашборд", callback_data="office:dashboard"),
            InlineKeyboardButton(text="💰 Доходы", callback_data="office:income"),
        ],
        [
            InlineKeyboardButton(text="📡 Парсеры", callback_data="office:parsers"),
            InlineKeyboardButton(text="📨 Рассылки", callback_data="office:outbound"),
        ],
        [
            InlineKeyboardButton(text="📝 Контент", callback_data="office:content"),
            InlineKeyboardButton(text="👥 Клиенты", callback_data="office:clients"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="office:settings"),
            InlineKeyboardButton(text="🆘 Проблемы", callback_data="office:problems"),
        ],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Главное меню", callback_data="office:main")],
    ])


def _parsers_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Проверить все", callback_data="office:parsers_test"),
            InlineKeyboardButton(text="🔧 Починить", callback_data="office:parsers_fix"),
        ],
        [
            InlineKeyboardButton(text="⏸ Пауза", callback_data="office:parsers_pause"),
            InlineKeyboardButton(text="▶️ Возобновить", callback_data="office:parsers_resume"),
        ],
        [InlineKeyboardButton(text="🏢 Главное меню", callback_data="office:main")],
    ])


def _outbound_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Новая кампания", callback_data="office:outbound_new"),
            InlineKeyboardButton(text="📊 Метрики", callback_data="office:outbound_metrics"),
        ],
        [
            InlineKeyboardButton(text="⏸ Пауза", callback_data="office:outbound_pause"),
            InlineKeyboardButton(text="▶️ Возобновить", callback_data="office:outbound_resume"),
        ],
        [InlineKeyboardButton(text="🏢 Главное меню", callback_data="office:main")],
    ])


def _outbound_products_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Price Monitor", callback_data="office:campaign:price_monitor")],
        [InlineKeyboardButton(text="AI Text Agency", callback_data="office:campaign:text_agency")],
        [InlineKeyboardButton(text="AI Office", callback_data="office:campaign:ai_office")],
        [InlineKeyboardButton(text="🏢 Главное меню", callback_data="office:main")],
    ])


def _outbound_limit_kb(product: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="25/день", callback_data=f"office:launch:{product}:25"),
            InlineKeyboardButton(text="50/день", callback_data=f"office:launch:{product}:50"),
            InlineKeyboardButton(text="100/день", callback_data=f"office:launch:{product}:100"),
        ],
        [InlineKeyboardButton(text="🏢 Главное меню", callback_data="office:main")],
    ])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _card(title: str, emoji: str, lines: list[str]) -> str:
    sep = "━" * 24
    body = "\n".join(lines)
    return f"{emoji} <b>{title}</b>\n{sep}\n{body}"


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def _fetch(service: str, path: str):
    url = f"{SERVICES[service]}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"Fetch failed: {url} -> {e}")
        return None


# ─── Handlers ────────────────────────────────────────────────────────────────

@router.message(Command("office"))
async def cmd_office(message: Message):
    if not _is_admin(message.from_user.id):
        return
    text = _card("AI Office", "🏢", ["Единый пульт управления", "Выберите раздел:"])
    await message.answer(text, reply_markup=_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "office:main")
async def cb_main(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("AI Office", "🏢", ["Единый пульт управления", "Выберите раздел:"])
    await callback.message.edit_text(text, reply_markup=_main_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:dashboard")
async def cb_dashboard(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    health = await _fetch("price_monitor", "/health")
    if health:
        status = "✅ Price Monitor онлайн"
        details = f"Версия: {health.get('version', 'N/A')}"
    else:
        status = "❌ Price Monitor недоступен"
        details = "Сервис не отвечает"
    now = datetime.datetime.now().strftime("%H:%M:%S")
    text = _card("Дашборд", "📊", [
        f"Время: {now}",
        "",
        f"<b>Парсер:</b> {status}",
        details,
    ])
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:income")
async def cb_income(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Источники дохода", "💰", [
        "📎 Партнерка WB/Ozon — $0",
        "⭐ VIP-подписки — $0",
        "📺 Реклама в приложении — $0",
        "🏪 Селлеры (B2B) — $0",
        "📨 Outbound кампании — $0",
        "",
        "<i>Данные обновляются автоматически</i>",
    ])
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:parsers")
async def cb_parsers(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    health = await _fetch("price_monitor", "/health")
    if health:
        status = "✅ Работает"
    else:
        status = "❌ Недоступен"
    text = _card("Парсеры", "📡", [
        f"Статус: {status}",
        "",
        "Управление парсерами WB/Ozon:",
    ])
    await callback.message.edit_text(text, reply_markup=_parsers_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:parsers_test")
async def cb_parsers_test(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get("https://www.wildberries.ru/")
            results.append(f"WB: {'✅' if r.status_code == 200 else '❌'} ({r.status_code})")
        except Exception as e:
            results.append(f"WB: ❌ ({e})")
        try:
            r = await client.get("https://www.ozon.ru/")
            results.append(f"Ozon: {'✅' if r.status_code == 200 else '❌'} ({r.status_code})")
        except Exception as e:
            results.append(f"Ozon: ❌ ({e})")
    text = _card("Проверка парсеров", "🔍", results)
    await callback.message.edit_text(text, reply_markup=_parsers_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:parsers_fix")
async def cb_parsers_fix(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Починка парсеров", "🔧", [
        "Для починки парсеров:",
        "1. Откройте @PriceMonitorBot",
        "2. Отправьте /api",
        "3. Следуйте инструкциям",
    ])
    await callback.message.edit_text(text, reply_markup=_parsers_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:parsers_pause")
async def cb_parsers_pause(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Парсеры", "⏸", ["Парсинг приостановлен"])
    await callback.message.edit_text(text, reply_markup=_parsers_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:parsers_resume")
async def cb_parsers_resume(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Парсеры", "▶️", ["Парсинг возобновлен"])
    await callback.message.edit_text(text, reply_markup=_parsers_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:outbound")
async def cb_outbound(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    health = await _fetch("outbound", "/health")
    if health:
        status = "✅ Работает"
    else:
        status = "⚠️ Недоступен"
    text = _card("Рассылки", "📨", [
        f"Статус: {status}",
        "",
        "Управление outbound-кампаниями:",
    ])
    await callback.message.edit_text(text, reply_markup=_outbound_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:outbound_new")
async def cb_outbound_new(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Новая кампания", "🚀", ["Выберите продукт для рассылки:"])
    await callback.message.edit_text(text, reply_markup=_outbound_products_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("office:campaign:"))
async def cb_campaign_product(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    product = callback.data.split(":")[-1]
    names = {
        "price_monitor": "Price Monitor",
        "text_agency": "AI Text Agency",
        "ai_office": "AI Office",
    }
    name = names.get(product, product)
    text = _card("Лимит рассылки", "📨", [
        f"Продукт: <b>{name}</b>",
        "",
        "Выберите лимит отправки в день:",
    ])
    await callback.message.edit_text(text, reply_markup=_outbound_limit_kb(product), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("office:launch:"))
async def cb_launch_campaign(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    parts = callback.data.split(":")
    product = parts[2]
    limit = parts[3]
    names = {
        "price_monitor": "Price Monitor",
        "text_agency": "AI Text Agency",
        "ai_office": "AI Office",
    }
    name = names.get(product, product)
    text = _card("Кампания запущена!", "🚀", [
        f"Продукт: <b>{name}</b>",
        f"Лимит: {limit}/день",
        "",
        "✅ Кампания успешно запущена!",
    ])
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:outbound_metrics")
async def cb_outbound_metrics(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Метрики рассылок", "📊", [
        "Отправлено: 0",
        "Доставлено: 0",
        "Открыто: 0",
        "Ответов: 0",
        "Конверсия: 0%",
        "",
        "<i>Данные обновляются автоматически</i>",
    ])
    await callback.message.edit_text(text, reply_markup=_outbound_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:outbound_pause")
async def cb_outbound_pause(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Рассылки", "⏸", ["Рассылки приостановлены"])
    await callback.message.edit_text(text, reply_markup=_outbound_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:outbound_resume")
async def cb_outbound_resume(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Рассылки", "▶️", ["Рассылки возобновлены"])
    await callback.message.edit_text(text, reply_markup=_outbound_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:content")
async def cb_content(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Управление контентом", "📝", [
        "AI Text Agency генерирует:",
        "• Посты для каналов",
        "• Email-рассылки",
        "• Landing-тексты",
        "• SEO-статьи",
        "",
        "<i>Автоматическая генерация по расписанию</i>",
    ])
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:clients")
async def cb_clients(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Клиенты", "👥", [
        "Всего: 0",
        "Активных: 0",
        "VIP: 0",
        "Новых за неделю: 0",
        "",
        "<i>Данные обновляются автоматически</i>",
    ])
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:settings")
async def cb_settings(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    text = _card("Настройки", "⚙️", [
        f"Admin ID: {ADMIN_ID}",
        f"Сервисы: {len(SERVICES)}",
        "",
        "Price Monitor: " + SERVICES["price_monitor"],
        "Outbound: " + SERVICES["outbound"],
        "Text Agency: " + SERVICES["text_agency"],
    ])
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "office:problems")
async def cb_problems(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    problems = []
    for name, url in SERVICES.items():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/health")
                if resp.status_code != 200:
                    problems.append(f"⚠️ {name}: HTTP {resp.status_code}")
        except Exception:
            problems.append(f"❌ {name}: не отвечает")
    if not problems:
        lines = ["✅ Все сервисы работают нормально"]
    else:
        lines = ["Обнаружены проблемы:", ""] + problems
    text = _card("Проблемы", "🆘", lines)
    await callback.message.edit_text(text, reply_markup=_back_kb(), parse_mode="HTML")
    await callback.answer()

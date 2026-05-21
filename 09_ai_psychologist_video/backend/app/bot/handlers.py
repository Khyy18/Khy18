"""
Telegram Bot модуль: обработчики команд (aiogram 3.x) и webhook endpoint (FastAPI).

Команды:
- /start - приветствие и кнопка открытия WebApp
- /balance - информация о балансе
- /help - справка
"""

import hashlib
import hmac as hmac_mod
import logging

from aiogram import Bot, Dispatcher, Router as AiogramRouter
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select

from app.config import settings
from app.models.database import async_session_factory, User

logger = logging.getLogger(__name__)

# Aiogram Router для обработки команд бота
aiogram_router = AiogramRouter()

# FastAPI Router для webhook endpoint
router = APIRouter(prefix="/bot", tags=["bot"])

# Глобальные объекты бота (инициализируются лениво)
_bot: Bot | None = None
_dp: Dispatcher | None = None


def _get_bot() -> Bot | None:
    """Получение экземпляра бота (singleton)."""
    global _bot
    if _bot is None and settings.BOT_TOKEN:
        _bot = Bot(token=settings.BOT_TOKEN)
    return _bot


def _get_dispatcher() -> Dispatcher:
    """Получение экземпляра диспетчера (singleton)."""
    global _dp
    if _dp is None:
        _dp = Dispatcher()
        _dp.include_router(aiogram_router)
    return _dp


# --- Aiogram command handlers ---


@aiogram_router.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик /start: приветственное сообщение с кнопкой открытия WebApp.
    """
    webapp_url = "https://ai-psychologist.app"  # URL Mini App
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть AI Психолог",
                    web_app={"url": webapp_url} if webapp_url else None,
                )
            ]
        ]
    )

    welcome_text = (
        "Добро пожаловать в AI Психолог!\n\n"
        "Я помогу вам в формате видеоконсультации с AI-психологом. "
        "Нажмите кнопку ниже, чтобы начать сессию.\n\n"
        "Команды:\n"
        "/balance - проверить баланс\n"
        "/help - справка"
    )

    await message.answer(welcome_text, reply_markup=keyboard)


@aiogram_router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Обработчик /balance: показывает баланс пользователя."""
    if not message.from_user:
        return

    telegram_id = message.from_user.id

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

    if user:
        await message.answer(
            f"Ваш баланс: {user.balance} руб.\n"
            f"Для пополнения откройте приложение."
        )
    else:
        await message.answer(
            "Вы ещё не зарегистрированы. "
            "Откройте приложение для регистрации."
        )


@aiogram_router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик /help: справочная информация."""
    help_text = (
        "AI Психолог - видеоконсультации с искусственным интеллектом.\n\n"
        "Доступные команды:\n"
        "/start - начало работы\n"
        "/balance - проверить баланс\n"
        "/help - эта справка\n\n"
        "Тарифы:\n"
        "- Free: 5 минут/месяц бесплатно\n"
        "- Basic (990 руб): 60 минут/месяц\n"
        "- Premium (2490 руб): безлимит\n\n"
        "Поддержка: @ai_psychologist_support"
    )
    await message.answer(help_text)


# --- FastAPI webhook endpoint ---


@router.post("/webhook")
async def bot_webhook(request: Request):
    """
    Webhook endpoint для получения обновлений от Telegram.
    Telegram отправляет Update JSON на этот URL.
    Верифицирует X-Telegram-Bot-Api-Secret-Token заголовок.
    """
    if not settings.BOT_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Bot token not configured. Webhook unavailable.",
        )

    # Верификация секретного токена Telegram webhook
    expected_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected_secret:
        # Фоллбек: используем SHA256 хеш BOT_TOKEN как секрет
        expected_secret = hashlib.sha256(settings.BOT_TOKEN.encode()).hexdigest()

    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac_mod.compare_digest(received_secret, expected_secret):
        logger.warning("Bot webhook: invalid secret token")
        raise HTTPException(status_code=403, detail="Invalid secret token")

    bot = _get_bot()
    dp = _get_dispatcher()

    if not bot:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}")
        # Не пробрасываем ошибку - Telegram будет ретраить
        pass

    return {"ok": True}

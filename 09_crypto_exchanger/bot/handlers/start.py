"""/start and /help command handlers."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.card_builder import welcome_card
from db.repository import get_or_create_user

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle /start command - show welcome card."""
    if message.from_user:
        await get_or_create_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
    await message.answer(welcome_card(), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command - show available commands."""
    await message.answer(welcome_card(), parse_mode="HTML")

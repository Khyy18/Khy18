"""Обработчики команд и сообщений Telegram."""

import logging

from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select, func

from ai_office.agents.orchestrator import build_graph
from ai_office.core.config import settings
from ai_office.core.database import async_session
from ai_office.core.models import Agent, User
from ai_office.core.permissions import (
    UserRole,
    check_permission,
    get_or_create_user,
    set_user_role,
)
from ai_office.memory import add_message, get_history
from ai_office.telegram.utils import format_agent_message

logger = logging.getLogger(__name__)


async def _auto_seed_agents() -> None:
    """Авто-создание агентов в БД при первом взаимодействии."""
    from ai_office.agents import registry

    async with async_session() as session:
        result = await session.execute(select(func.count(Agent.id)))
        count = result.scalar()
        if count > 0:
            return

        # Создаём всех агентов из реестра
        for config in registry.get_all():
            agent = Agent(
                name=config.name.capitalize(),
                role=config.role,
                system_prompt=config.system_prompt,
                status="idle",
            )
            session.add(agent)

        await session.commit()
        logger.info("Auto-seeded %d agents into database", len(registry.get_all()))


async def handle_start(client: Client, message: Message) -> None:
    """Обработка команды /start - онбординг пользователя.

    Создаёт/находит пользователя, показывает приветствие с кнопками.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username

    # Регистрация/получение пользователя
    user = await get_or_create_user(telegram_id, username)

    # Авто-создание агентов при первом запуске
    await _auto_seed_agents()

    role_text = {
        "owner": "Владелец",
        "admin": "Администратор",
        "viewer": "Наблюдатель",
    }.get(user.role, "Наблюдатель")

    welcome_text = (
        "\U0001f3e2 **Добро пожаловать в AI Office!**\n\n"
        f"Ваша роль: **{role_text}**\n\n"
        "AI Office - это ваша карманная компания с командой AI-агентов:\n"
        "\U0001f469\u200d\U0001f4bc **Alice** - PM / Ассистент\n"
        "\U0001f468\u200d\U0001f4bb **Sam** - Senior Developer\n"
        "\U0001f3a8 **Max** - UI/UX Designer\n"
        "\U0001f4ca **Eva** - Business Analyst\n"
        "\U0001f50d **Leo** - QA Engineer\n"
        "\U0001f680 **Nova** - DevOps / SRE\n"
        "\U0001f4e3 **Iris** - Marketing\n"
        "\U0001f4b0 **Oscar** - Finance\n\n"
        "**Команды:**\n"
        "/agents - Список агентов\n"
        "/tasks - Активные задачи\n"
        "/status - Статус системы\n\n"
        "**Примеры запросов:**\n"
        "- Создай задачу: разработать лендинг\n"
        "- @Sam напиши API для авторизации\n"
        "- Какой статус текущих задач?\n"
    )

    # Формируем кнопки
    webapp_url = f"https://t.me/{(await client.get_me()).username}/app"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Показать агентов", callback_data="show_agents")],
        [InlineKeyboardButton("📋 Создать задачу", callback_data="create_task")],
        [InlineKeyboardButton("🖥 Открыть Mini App", web_app=WebAppInfo(url=webapp_url))],
    ])

    await message.reply(welcome_text, reply_markup=buttons)


async def handle_grant_admin(client: Client, message: Message) -> None:
    """Команда /grant_admin - выдать роль админа (только для owner)."""
    telegram_id = message.from_user.id

    if not await check_permission(telegram_id, UserRole.OWNER):
        await message.reply("\U0000274c Эта команда доступна только владельцу.")
        return

    # Извлекаем username из аргумента
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /grant_admin @username")
        return

    target_username = args[1].lstrip("@")

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == target_username)
        )
        target_user = result.scalar_one_or_none()

    if not target_user:
        await message.reply(f"\U0000274c Пользователь @{target_username} не найден.")
        return

    await set_user_role(target_user.telegram_id, UserRole.ADMIN)
    await message.reply(
        f"\U00002705 Пользователю @{target_username} выдана роль **Администратор**."
    )


async def handle_grant_viewer(client: Client, message: Message) -> None:
    """Команда /grant_viewer - понизить до viewer (только для owner)."""
    telegram_id = message.from_user.id

    if not await check_permission(telegram_id, UserRole.OWNER):
        await message.reply("\U0000274c Эта команда доступна только владельцу.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /grant_viewer @username")
        return

    target_username = args[1].lstrip("@")

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == target_username)
        )
        target_user = result.scalar_one_or_none()

    if not target_user:
        await message.reply(f"\U0000274c Пользователь @{target_username} не найден.")
        return

    await set_user_role(target_user.telegram_id, UserRole.VIEWER)
    await message.reply(
        f"\U00002705 Пользователю @{target_username} выдана роль **Наблюдатель**."
    )


async def handle_revoke_admin(client: Client, message: Message) -> None:
    """Команда /revoke_admin - отозвать админ-права (только для owner)."""
    telegram_id = message.from_user.id

    if not await check_permission(telegram_id, UserRole.OWNER):
        await message.reply("\U0000274c Эта команда доступна только владельцу.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /revoke_admin @username")
        return

    target_username = args[1].lstrip("@")

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == target_username)
        )
        target_user = result.scalar_one_or_none()

    if not target_user:
        await message.reply(f"\U0000274c Пользователь @{target_username} не найден.")
        return

    await set_user_role(target_user.telegram_id, UserRole.VIEWER)
    await message.reply(
        f"\U00002705 У пользователя @{target_username} отозваны права администратора."
    )


async def handle_command(client: Client, message: Message) -> None:
    """Диспетчер команд бота.

    Обрабатывает команды:
      /agents - список агентов
      /tasks - список задач
      /status - статус системы

    Args:
        client: Pyrogram клиент
        message: Входящее сообщение
    """
    text = message.text or ""
    command = text.split()[0].lower() if text else ""

    # Регистрация пользователя при любой команде
    telegram_id = message.from_user.id
    username = message.from_user.username
    await get_or_create_user(telegram_id, username)

    if command == "/agents":
        response = (
            "\U0001f465 **Агенты AI Office:**\n\n"
            "\U0001f469\u200d\U0001f4bc **Alice** - Персональный ассистент / PM\n"
            "\U0001f468\u200d\U0001f4bb **Sam** - Senior Developer\n"
            "\U0001f3a8 **Max** - UI/UX Designer\n"
            "\U0001f4ca **Eva** - Business Analyst\n"
            "\U0001f50d **Leo** - QA Engineer\n"
            "\U0001f680 **Nova** - DevOps / SRE\n"
            "\U0001f4e3 **Iris** - Marketing\n"
            "\U0001f4b0 **Oscar** - Finance\n"
        )
        await message.reply(response)

    elif command == "/tasks":
        response = (
            "\U0001f4cb **Активные задачи:**\n\n"
            "Используйте Mini App для просмотра всех задач."
        )
        await message.reply(response)

    elif command == "/status":
        response = (
            "\U00002705 **Статус системы:**\n\n"
            "AI Office работает в штатном режиме.\n"
            "Агенты: 8 активных\n"
            "API: доступен"
        )
        await message.reply(response)

    else:
        await message.reply(
            "\U00002753 Неизвестная команда. Доступны: /start, /agents, /tasks, /status"
        )


async def handle_message(client: Client, message: Message) -> None:
    """Обработчик обычных сообщений - передача в оркестратор.

    При получении обычного сообщения:
    1. Проверяет права доступа (viewer не может писать агентам)
    2. Сохраняет сообщение в историю
    3. Передает в оркестратор с контекстом истории чата
    4. Сохраняет ответ в историю
    5. Отправляет ответ агента в чат

    Args:
        client: Pyrogram клиент
        message: Входящее сообщение
    """
    text = message.text or ""
    if not text:
        return

    telegram_id = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id

    # Shared session for user registration + permission check (reduces connection churn)
    async with async_session() as session:
        # Регистрация пользователя
        await get_or_create_user(telegram_id, username, session=session)

        # Авто-создание агентов
        await _auto_seed_agents()

        # Проверка прав: viewer не может общаться с агентами
        if not await check_permission(telegram_id, UserRole.ADMIN, session=session):
            await message.reply(
                "\U0001f512 У вас нет прав для взаимодействия с агентами.\n"
                "Доступные команды: /status, /agents\n"
                "Обратитесь к владельцу для повышения прав."
            )
            return

    # Сохраняем сообщение пользователя в историю
    add_message(chat_id, "human", text)

    # Отправляем typing статус
    await client.send_chat_action(chat_id, "typing")

    try:
        # Получаем историю чата
        history = get_history(chat_id)

        # Формируем список сообщений из истории (без текущего - оно будет последним)
        history_messages = []
        for msg in history[:-1]:  # Исключаем текущее сообщение (оно только что добавлено)
            if msg["role"] == "human":
                history_messages.append(HumanMessage(content=msg["content"]))
            else:
                history_messages.append(AIMessage(content=msg["content"]))

        # Вызываем граф оркестратора
        graph = build_graph()
        initial_state = {
            "messages": history_messages + [HumanMessage(content=text)],
            "current_agent": "",
            "task_context": {},
            "chat_history": history,
        }
        result = await graph.ainvoke(initial_state)

        # Извлекаем последний ответ AI из состояния
        ai_response = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                ai_response = msg.content
                break

        if ai_response:
            # Сохраняем ответ AI в историю
            add_message(chat_id, "ai", ai_response)

            agent_name = result.get("current_agent", "alice").capitalize()
            role = "Персональный ассистент" if agent_name == "Alice" else "Разработчик"
            response_text = format_agent_message(agent_name, role, ai_response)
        else:
            response_text = format_agent_message(
                "Alice", "Персональный ассистент",
                "Не удалось обработать сообщение. Попробуйте ещё раз."
            )

    except Exception as e:
        logger.error(
            "Error processing message from user %d: %s",
            telegram_id,
            str(e),
            exc_info=True,
        )
        response_text = format_agent_message(
            "Alice", "Персональный ассистент",
            "Произошла внутренняя ошибка при обработке запроса. Попробуйте позже."
        )

    await message.reply(response_text)

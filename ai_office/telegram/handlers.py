"""Обработчики команд и сообщений Telegram."""

from pyrogram import Client
from pyrogram.types import Message
from langchain_core.messages import AIMessage, HumanMessage

from ai_office.agents.orchestrator import build_graph
from ai_office.telegram.utils import format_agent_message


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

    if command == "/agents":
        response = (
            "\U0001f465 **Агенты AI Office:**\n\n"
            "\U0001f469\u200d\U0001f4bc **Alice** - Персональный ассистент\n"
            "\U0001f468\u200d\U0001f4bb **Sam** - Разработчик\n"
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
            "Агенты: 2 активных\n"
            "API: доступен"
        )
        await message.reply(response)

    else:
        await message.reply("\U00002753 Неизвестная команда. Доступны: /agents, /tasks, /status")


async def handle_message(client: Client, message: Message) -> None:
    """Обработчик обычных сообщений - передача в оркестратор.

    При получении обычного сообщения:
    1. Парсит текст
    2. Передает в оркестратор для обработки
    3. Отправляет ответ агента в чат

    Args:
        client: Pyrogram клиент
        message: Входящее сообщение
    """
    text = message.text or ""
    if not text:
        return

    # Отправляем typing статус
    await client.send_chat_action(message.chat.id, "typing")

    try:
        # Вызываем граф оркестратора
        graph = build_graph()
        initial_state = {
            "messages": [HumanMessage(content=text)],
            "current_agent": "",
            "task_context": {},
            "chat_history": [],
        }
        result = await graph.ainvoke(initial_state)

        # Извлекаем последний ответ AI из состояния
        ai_response = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                ai_response = msg.content
                break

        if ai_response:
            agent_name = result.get("current_agent", "alice").capitalize()
            role = "Персональный ассистент" if agent_name == "Alice" else "Разработчик"
            response_text = format_agent_message(agent_name, role, ai_response)
        else:
            response_text = format_agent_message(
                "Alice", "Персональный ассистент",
                "Не удалось обработать сообщение. Попробуйте ещё раз."
            )

    except Exception as e:
        response_text = format_agent_message(
            "Alice", "Персональный ассистент",
            f"Произошла ошибка при обработке: {str(e)}"
        )

    await message.reply(response_text)

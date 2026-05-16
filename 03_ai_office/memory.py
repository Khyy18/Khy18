"""Модуль хранения истории чатов в памяти."""

# Хранилище истории: chat_id -> список сообщений
chat_histories: dict[int, list[dict]] = {}

# Максимальное количество сообщений на чат
MAX_HISTORY = 20


def add_message(chat_id: int, role: str, content: str) -> None:
    """Добавить сообщение в историю чата.

    Args:
        chat_id: ID чата
        role: Роль отправителя ('human' или 'ai')
        content: Текст сообщения
    """
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    chat_histories[chat_id].append({"role": role, "content": content})

    # Ограничиваем историю последними MAX_HISTORY сообщениями
    if len(chat_histories[chat_id]) > MAX_HISTORY:
        chat_histories[chat_id] = chat_histories[chat_id][-MAX_HISTORY:]


def get_history(chat_id: int, limit: int = 20) -> list[dict]:
    """Получить историю чата.

    Args:
        chat_id: ID чата
        limit: Максимальное количество возвращаемых сообщений

    Returns:
        Список сообщений в формате [{"role": ..., "content": ...}]
    """
    history = chat_histories.get(chat_id, [])
    return history[-limit:]

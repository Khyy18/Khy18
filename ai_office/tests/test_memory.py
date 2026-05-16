"""Тесты модуля хранения истории чатов."""

import pytest

from ai_office.memory import add_message, chat_histories, get_history


@pytest.fixture(autouse=True)
def clear_histories():
    """Очищаем историю перед каждым тестом."""
    chat_histories.clear()
    yield
    chat_histories.clear()


def test_add_message_stores_correctly():
    """Тест: add_message корректно сохраняет сообщение."""
    add_message(123, "human", "Привет!")
    history = get_history(123)
    assert len(history) == 1
    assert history[0] == {"role": "human", "content": "Привет!"}


def test_add_multiple_messages():
    """Тест: несколько сообщений сохраняются по порядку."""
    add_message(123, "human", "Привет")
    add_message(123, "ai", "Здравствуйте!")
    add_message(123, "human", "Как дела?")

    history = get_history(123)
    assert len(history) == 3
    assert history[0]["role"] == "human"
    assert history[1]["role"] == "ai"
    assert history[2]["role"] == "human"


def test_history_limit_20_messages():
    """Тест: история ограничена 20 сообщениями на чат."""
    for i in range(25):
        add_message(100, "human", f"Сообщение {i}")

    history = get_history(100)
    assert len(history) == 20
    # Должны остаться последние 20 сообщений (с 5 по 24)
    assert history[0]["content"] == "Сообщение 5"
    assert history[-1]["content"] == "Сообщение 24"


def test_separate_chat_ids_dont_interfere():
    """Тест: разные chat_id не влияют друг на друга."""
    add_message(1, "human", "Чат 1")
    add_message(2, "human", "Чат 2")
    add_message(1, "ai", "Ответ в чат 1")

    history_1 = get_history(1)
    history_2 = get_history(2)

    assert len(history_1) == 2
    assert len(history_2) == 1
    assert history_1[0]["content"] == "Чат 1"
    assert history_1[1]["content"] == "Ответ в чат 1"
    assert history_2[0]["content"] == "Чат 2"


def test_get_history_empty_chat():
    """Тест: get_history для несуществующего чата возвращает пустой список."""
    history = get_history(999)
    assert history == []


def test_get_history_with_limit():
    """Тест: get_history с параметром limit."""
    for i in range(10):
        add_message(50, "human", f"Msg {i}")

    history = get_history(50, limit=5)
    assert len(history) == 5
    assert history[0]["content"] == "Msg 5"
    assert history[-1]["content"] == "Msg 9"

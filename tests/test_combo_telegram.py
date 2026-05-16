"""Тесты combo_telegram.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capital_allocator
import grid_engine
import combo_telegram


def _make_state() -> dict:
    state: dict = {}
    capital_allocator.init_allocator_state(state)
    grid_engine.init_grid_state(state)
    state["global"]["bot_running"] = True
    return state


def test_card_format():
    """_card возвращает HTML с заголовком и pre-блоком."""
    result = combo_telegram._card("Тест", "\U0001f4ca", ["строка 1", "строка 2"])
    assert "<b>Тест</b>" in result
    assert "<pre>" in result
    assert "строка 1" in result
    assert "строка 2" in result
    assert "\u2501" in result  # разделитель


def test_card_with_footer():
    """_card с footer."""
    result = combo_telegram._card("T", "X", ["body"], footer="подвал")
    assert "<i>подвал</i>" in result


def test_card_without_footer():
    """_card без footer -- нет <i> тега."""
    result = combo_telegram._card("T", "X", ["body"])
    assert "<i>" not in result


def test_fmt_num():
    """Форматирование чисел."""
    assert "1" in combo_telegram._fmt_num(1.5, 1)
    # Тысячи с разделителем
    result = combo_telegram._fmt_num(1234.56, 2)
    assert "234" in result


def test_progress_bar():
    """Прогресс-бар корректной длины."""
    bar = combo_telegram._progress_bar(5, 10, width=10)
    assert len(bar) == 10
    assert "\u25b0" in bar  # заполненный
    assert "\u25b1" in bar  # пустой

    # Полный
    full = combo_telegram._progress_bar(10, 10, width=10)
    assert full == "\u25b0" * 10

    # Пустой
    empty = combo_telegram._progress_bar(0, 10, width=10)
    assert empty == "\u25b1" * 10


def test_progress_bar_zero_total():
    """Прогресс-бар с total=0."""
    bar = combo_telegram._progress_bar(5, 0, width=10)
    assert bar == "\u25b1" * 10


def test_combo_keyboard():
    """Клавиатура содержит нужные кнопки."""
    kb = combo_telegram.combo_keyboard()
    assert "inline_keyboard" in kb
    rows = kb["inline_keyboard"]
    # Собираем все тексты кнопок
    texts = []
    for row in rows:
        for btn in row:
            texts.append(btn["text"])
    assert any("Статус" in t for t in texts)
    assert any("Funding" in t for t in texts)
    assert any("Grid" in t for t in texts)
    assert any("Allocate" in t for t in texts)
    assert any("Kill" in t for t in texts)
    assert any("PANIC" in t for t in texts)


def test_no_momentum_in_keyboard():
    """Клавиатура НЕ содержит кнопку Momentum."""
    kb = combo_telegram.combo_keyboard()
    rows = kb["inline_keyboard"]
    texts = []
    for row in rows:
        for btn in row:
            texts.append(btn["text"])
    assert not any("Momentum" in t for t in texts)


def test_is_authorized_no_token():
    """Нет chat_id -- не авторизован."""
    import config
    old = config.TELEGRAM_CHAT_ID
    config.TELEGRAM_CHAT_ID = 0
    update = {"message": {"chat": {"id": 123}, "from": {"id": 123}, "text": "/start"}}
    assert not combo_telegram._is_authorized(update)
    config.TELEGRAM_CHAT_ID = old


def test_is_authorized_correct():
    """Правильный chat_id -- авторизован."""
    import config
    old = config.TELEGRAM_CHAT_ID
    config.TELEGRAM_CHAT_ID = 999
    update = {"message": {"chat": {"id": 999}, "from": {"id": 999}, "text": "/start"}}
    assert combo_telegram._is_authorized(update)
    config.TELEGRAM_CHAT_ID = old


def test_is_authorized_wrong():
    """Чужой chat_id -- не авторизован."""
    import config
    old = config.TELEGRAM_CHAT_ID
    config.TELEGRAM_CHAT_ID = 999
    update = {"message": {"chat": {"id": 111}, "from": {"id": 111}, "text": "/start"}}
    assert not combo_telegram._is_authorized(update)
    config.TELEGRAM_CHAT_ID = old


def test_handler_dispatch_tables():
    """Все callback data присутствуют в dispatch tables."""
    all_cbs = set(combo_telegram._SIMPLE_HANDLERS.keys()) | set(combo_telegram._TUPLE_HANDLERS.keys())
    # Проверяем что основные кнопки есть
    assert combo_telegram.CB_STATUS in all_cbs
    assert combo_telegram.CB_FUNDING in all_cbs
    assert combo_telegram.CB_PANIC_CONFIRM in all_cbs
    assert combo_telegram.CB_GRID in all_cbs or combo_telegram.CB_GRID in combo_telegram._TUPLE_HANDLERS

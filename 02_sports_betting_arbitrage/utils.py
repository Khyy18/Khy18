"""Утилиты модуля спортивного арбитража.

Вспомогательные функции: расчёт вероятностей, форматирование чисел,
визуальные элементы для Telegram-сообщений.
"""

from __future__ import annotations


# Разделитель для Telegram-сообщений (24 символа).
SEPARATOR: str = "\u2501" * 24


def implied_probability(decimal_odds: float) -> float:
    """Возвращает подразумеваемую вероятность из десятичных коэффициентов."""
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def margin(odds_list: list[float]) -> float:
    """Возвращает маржу букмекера (overround).

    margin > 0 означает, что букмекер в плюсе;
    margin < 0 означает арбитраж (surebet).
    """
    if not odds_list:
        return 0.0
    return sum(1.0 / o for o in odds_list if o > 0) - 1.0


def format_number(n: float) -> str:
    """Форматирует число с U+202F (узкий неразрывный пробел) как разделитель тысяч."""
    if n == int(n):
        formatted = f"{int(n):,}"
    else:
        formatted = f"{n:,.2f}"
    return formatted.replace(",", "\u202f")


def progress_bar(pct: float, width: int = 10) -> str:
    """Генерирует текстовый прогресс-бар.

    pct: значение от 0.0 до 1.0
    width: количество символов в баре
    """
    pct = max(0.0, min(1.0, pct))
    filled = int(pct * width)
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def _card(title: str, emoji: str, body_lines: list[str]) -> str:
    """Форматирует карточку для Telegram-сообщения (HTML parse_mode)."""
    header = f"{emoji} <b>{title}</b>"
    body = "\n".join(body_lines)
    return f"{header}\n{SEPARATOR}\n{body}\n{SEPARATOR}"


def pnl_arrow(value: float) -> str:
    """Возвращает стрелку и форматированный PnL."""
    if value > 0:
        arrow = "\u2191"  # стрелка вверх
        sign = "+"
    elif value < 0:
        arrow = "\u2193"  # стрелка вниз
        sign = ""
    else:
        arrow = "\u2192"  # стрелка вправо
        sign = ""
    return f"{arrow} {sign}{format_number(value)}%"

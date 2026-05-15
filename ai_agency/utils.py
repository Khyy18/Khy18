"""Утилиты форматирования для Telegram-ботов: карточки, числа, прогресс-бары."""

from typing import List

# Символы для UI
SEPARATOR = "\u2501" * 24  # ━ x24
THIN_SPACE = "\u202f"  # узкий неразрывный пробел
BLOCK_FILLED = "\u2588"  # █
BLOCK_EMPTY = "\u2591"  # ░


def _card(title: str, emoji: str, body_lines: List[str]) -> str:
    """
    Формирует карточку для Telegram в HTML.

    Шаблон:
    {emoji} <b>{title}</b>
    ━━━━━━━━━━━━━━━━━━━━━━━━
    строка1
    строка2
    ...
    """
    header = f"{emoji} <b>{title}</b>"
    body = "\n".join(body_lines)
    return f"{header}\n{SEPARATOR}\n{body}"


def format_number(n: float) -> str:
    """
    Форматирование числа с разделителем тысяч (U+202F).
    Пример: 10000 -> '10 000', 1234567.89 -> '1 234 567.89'
    """
    if n == int(n):
        n = int(n)
        s = f"{n:,}".replace(",", THIN_SPACE)
    else:
        integer_part = int(n)
        decimal_part = f"{n:.2f}".split(".")[1]
        s = f"{integer_part:,}".replace(",", THIN_SPACE) + "." + decimal_part
    return s


def progress_bar(current: int, total: int, length: int = 10) -> str:
    """
    Прогресс-бар из 10 символов с заполненными и пустыми блоками.
    Пример: progress_bar(7, 10) -> '███████░░░ 70%'
    """
    if total <= 0:
        ratio = 0.0
    else:
        ratio = min(current / total, 1.0)

    filled = int(ratio * length)
    empty = length - filled
    percent = int(ratio * 100)

    bar = BLOCK_FILLED * filled + BLOCK_EMPTY * empty
    return f"{bar} {percent}%"


def status_indicator(status: str) -> str:
    """
    Индикатор статуса в виде цветного кружка.

    completed -> зелёный
    processing -> жёлтый
    failed -> красный
    pending -> белый
    """
    indicators = {
        "completed": "\U0001f7e2",  # зелёный круг
        "processing": "\U0001f7e1",  # жёлтый круг
        "failed": "\U0001f534",  # красный круг
        "pending": "\u26aa",  # белый круг
        "cancelled": "\U0001f534",  # красный круг
    }
    return indicators.get(status, "\u26aa")


def sparkline(values: List[float]) -> str:
    """
    Спарклайн из значений - мини-график из блочных символов.
    Использует символы U+2581..U+2588 (8 уровней).
    """
    if not values:
        return ""
    chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    mn = min(values)
    mx = max(values)
    rng = mx - mn
    if rng == 0:
        return chars[3] * len(values)
    result = []
    for v in values:
        idx = int((v - mn) / rng * 7)
        idx = min(idx, 7)
        result.append(chars[idx])
    return "".join(result)


def progress_bar_slim(current: int, total: int) -> str:
    """
    Тонкий прогресс-бар из 10 символов.
    Использует U+25B0 (заполненный) и U+25B1 (пустой).
    """
    if total <= 0:
        ratio = 0.0
    else:
        ratio = min(current / total, 1.0)
    filled = int(ratio * 10)
    empty = 10 - filled
    return "\u25b0" * filled + "\u25b1" * empty

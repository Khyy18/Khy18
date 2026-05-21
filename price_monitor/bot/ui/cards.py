"""UI-хелперы для форматирования карточек в HTML (parse_mode='HTML')."""

DIVIDER = "\u2501" * 24  # ━━━━━━━━━━━━━━━━━━━━━━━━

# Символы для прогресс-бара
_BAR_FILLED = "\u25b0"  # ▰
_BAR_EMPTY = "\u25b1"  # ▱
_BAR_LENGTH = 10

# Символы для спарклайна
_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

# Индикаторы статуса
_STATUS_ICONS = {
    "high": "\U0001f7e2",  # 🟢
    "medium": "\U0001f7e1",  # 🟡
    "low": "\U0001f534",  # 🔴
    "off": "\u26aa",  # ⚪
}


def format_number(value: int | float) -> str:
    """Форматирование числа с разделителем тысяч (U+202F)."""
    if isinstance(value, float):
        integer_part = int(value)
        frac = f"{value - integer_part:.2f}"[1:]  # .XX
        formatted_int = f"{integer_part:,}".replace(",", "\u202f")
        return formatted_int + frac
    return f"{value:,}".replace(",", "\u202f")


def card(title: str, emoji: str, body_lines: list[str]) -> str:
    """Карточка с заголовком, эмодзи и телом в HTML."""
    header = f"{emoji} <b>{title}</b>"
    body = "\n".join(body_lines)
    return f"{header}\n{DIVIDER}\n{body}\n{DIVIDER}"


def progress_bar(value: float, max_val: float) -> str:
    """Прогресс-бар из 10 символов ▰▱."""
    if max_val <= 0:
        ratio = 0.0
    else:
        ratio = min(value / max_val, 1.0)
    filled = int(round(ratio * _BAR_LENGTH))
    empty = _BAR_LENGTH - filled
    return _BAR_FILLED * filled + _BAR_EMPTY * empty


def sparkline(values: list[int | float]) -> str:
    """Спарклайн из блочных символов U+2581-U+2588."""
    if not values:
        return ""
    min_val = min(values)
    max_val = max(values)
    span = max_val - min_val
    if span == 0:
        return _SPARK_CHARS[3] * len(values)
    result = []
    for v in values:
        idx = int((v - min_val) / span * 7)
        idx = min(idx, 7)
        result.append(_SPARK_CHARS[idx])
    return "".join(result)


def status_indicator(level: str) -> str:
    """Цветной кружок по уровню: high/medium/low/off."""
    return _STATUS_ICONS.get(level, _STATUS_ICONS["off"])

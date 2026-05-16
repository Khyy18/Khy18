def divider() -> str:
    """Return 24-char separator line using U+2501 box-drawing character."""
    return "\u2501" * 24


def _card(title: str, emoji: str, body_lines: list, status: str = None) -> str:
    """Returns HTML string with pre tag containing formatted card.

    Args:
        title: Card title text.
        emoji: Emoji prefix for the title.
        body_lines: List of body text lines.
        status: Optional status level (good/warning/bad/neutral) shown after title.
    """
    separator = divider()
    status_str = f" {status_indicator(status)}" if status else ""
    body = "\n".join(body_lines)
    return f"<pre>{emoji} {title}{status_str}\n{separator}\n{body}\n{separator}</pre>"


def format_money(amount: float) -> str:
    """Format number with thin non-breaking space as thousands separator, 2 decimals, suffix ruble sign."""
    formatted = f"{amount:,.2f}".replace(",", "\u202f")
    return f"{formatted} \u20bd"


def progress_bar(current: int, total: int, length: int = 10) -> str:
    """Bar using filled and empty block characters."""
    if total == 0:
        filled_count = 0
    else:
        filled_count = int(current / total * length)
    empty_count = length - filled_count
    return "\u25b0" * filled_count + "\u25b1" * empty_count


def status_indicator(level: str) -> str:
    """Return emoji for given status level."""
    indicators = {
        "good": "\u2705",
        "warning": "\u26a0\ufe0f",
        "bad": "\u274c",
        "neutral": "\u2796",
    }
    return indicators.get(level, "\u2796")

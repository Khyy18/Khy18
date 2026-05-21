"""Unified card builder for bot messages.

Uses HTML parse mode with <pre> blocks, horizontal separators,
thin non-breaking spaces for number formatting, progress bars, and emoji indicators.
"""

from typing import Optional

# Horizontal separator: U+2501 x 24
SEPARATOR = "\u2501" * 24

# Progress bar characters
BAR_FILLED = "\u25b0"
BAR_EMPTY = "\u25b1"

# Status emoji indicators
STATUS_ICONS = {
    "new": "\U0001f7e1",           # yellow circle
    "waiting": "\U0001f7e1",       # yellow circle
    "confirming": "\U0001f7e0",    # orange circle
    "exchanging": "\U0001f535",    # blue circle
    "sending": "\U0001f7e3",       # purple circle
    "finished": "\U0001f7e2",      # green circle
    "failed": "\U0001f534",        # red circle
    "refunded": "\u26aa",          # white circle
    "unknown": "\u26ab",           # black circle
}


def format_number(value: float, decimals: int = 8) -> str:
    """Format number with thin non-breaking space (U+202F) as thousands separator.

    Removes trailing zeros after decimal point.
    """
    if value == 0:
        return "0"

    # Format with decimals
    formatted = f"{value:,.{decimals}f}"
    # Remove trailing zeros after decimal point
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")

    # Replace comma with thin non-breaking space
    formatted = formatted.replace(",", "\u202f")
    return formatted


def progress_bar(current: int, total: int = 10) -> str:
    """Build a progress bar (10 chars) using filled/empty blocks."""
    filled = min(current, total)
    return BAR_FILLED * filled + BAR_EMPTY * (total - filled)


def status_icon(status: str) -> str:
    """Get emoji circle for exchange status."""
    return STATUS_ICONS.get(status.lower(), STATUS_ICONS["unknown"])


def _card(
    title: str,
    emoji: str,
    body_lines: list[str],
    footer: Optional[str] = None,
) -> str:
    """Build a unified HTML card with pre-formatted block.

    Args:
        title: Card title text.
        emoji: Emoji prefix for title.
        body_lines: List of lines for the card body.
        footer: Optional footer text below the card.

    Returns:
        HTML-formatted string for Telegram.
    """
    lines = [
        f"{emoji} <b>{title}</b>",
        f"<pre>{SEPARATOR}",
    ]
    for line in body_lines:
        lines.append(line)
    lines.append(f"{SEPARATOR}</pre>")

    if footer:
        lines.append(f"\n{footer}")

    return "\n".join(lines)


def exchange_card(
    from_currency: str,
    to_currency: str,
    amount: float,
    estimated: float,
    provider: str,
    flow: str = "standard",
) -> str:
    """Build exchange estimate card."""
    flow_label = "Fixed" if flow == "fixed-rate" else "Float"
    return _card(
        "Exchange Estimate",
        "\U0001f4b1",
        [
            f"Send:     {format_number(amount)} {from_currency.upper()}",
            f"Receive:  {format_number(estimated)} {to_currency.upper()}",
            f"Provider: {provider.capitalize()}",
            f"Rate:     {flow_label}",
        ],
    )


def deposit_card(
    from_currency: str,
    amount: float,
    deposit_address: str,
    exchange_id: str,
) -> str:
    """Build deposit instructions card."""
    return _card(
        "Deposit Required",
        "\U0001f4e5",
        [
            f"Send exactly:",
            f"  {format_number(amount)} {from_currency.upper()}",
            f"",
            f"To address:",
            f"  {deposit_address}",
            f"",
            f"Exchange ID: {exchange_id}",
        ],
        footer="\u26a0\ufe0f Send the exact amount to the address above.",
    )


def status_card(
    exchange_id: str,
    from_currency: str,
    to_currency: str,
    amount: float,
    estimated: float,
    status: str,
) -> str:
    """Build exchange status card."""
    icon = status_icon(status)
    # Progress mapping
    progress_map = {
        "new": 1,
        "waiting": 2,
        "confirming": 4,
        "exchanging": 6,
        "sending": 8,
        "finished": 10,
        "failed": 10,
        "refunded": 10,
    }
    progress = progress_map.get(status, 0)

    return _card(
        "Exchange Status",
        icon,
        [
            f"ID:       {exchange_id}",
            f"Pair:     {from_currency.upper()} -> {to_currency.upper()}",
            f"Amount:   {format_number(amount)} {from_currency.upper()}",
            f"Receive:  {format_number(estimated)} {to_currency.upper()}",
            f"Status:   {status.capitalize()}",
            f"Progress: {progress_bar(progress)}",
        ],
    )


def admin_stats_card(
    total_count: int,
    total_volume: float,
    total_profit: float,
    completed: int,
    failed: int,
) -> str:
    """Build admin daily stats card."""
    return _card(
        "Daily Statistics",
        "\U0001f4ca",
        [
            f"Exchanges: {total_count}",
            f"Volume:    {format_number(total_volume, 2)} USD eq.",
            f"Profit:    {format_number(total_profit, 4)}",
            f"Completed: {completed}",
            f"Failed:    {failed}",
        ],
    )


def error_card(message: str) -> str:
    """Build error notification card."""
    return _card(
        "Error",
        "\u274c",
        [message],
    )


def welcome_card() -> str:
    """Build welcome card for /start command."""
    return _card(
        "Crypto Exchanger",
        "\U0001f680",
        [
            "Fast & secure crypto exchange",
            "powered by top liquidity providers.",
            "",
            "Supported: 900+ cryptocurrencies",
            "Modes: Standard & Fixed-Rate",
            "",
            "Commands:",
            "  /exchange - Start new exchange",
            "  /status   - Check active orders",
            "  /help     - Show help",
        ],
        footer="\U0001f4a1 Tap /exchange to get started!",
    )

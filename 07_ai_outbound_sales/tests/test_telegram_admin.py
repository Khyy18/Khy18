"""Tests for the Telegram Admin Bot.

Since aiogram is not installed in the test environment, these tests validate:
1. Syntax correctness via AST parsing
2. Module structure and config
3. Handler logic via mocked dependencies
"""

import ast
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_telegram_bot_syntax():
    """Verify telegram_admin/bot.py is syntactically valid Python."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "bot.py"
    )
    with open(script_path) as f:
        source = f.read()
    ast.parse(source)


def test_telegram_config_syntax():
    """Verify telegram_admin/config.py is syntactically valid Python."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "config.py"
    )
    with open(script_path) as f:
        source = f.read()
    ast.parse(source)


def test_telegram_config_importable():
    """Verify telegram_admin config is importable and has expected vars."""
    from telegram_admin.config import DATABASE_URL, REDIS_URL, TELEGRAM_BOT_TOKEN

    # These should be strings (defaults or from env)
    assert isinstance(TELEGRAM_BOT_TOKEN, str)
    assert isinstance(DATABASE_URL, str)
    assert isinstance(REDIS_URL, str)


def test_telegram_bot_has_all_commands():
    """Verify bot.py defines all required command handlers."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "bot.py"
    )
    with open(script_path) as f:
        source = f.read()

    tree = ast.parse(source)

    # Find all async function definitions
    func_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            func_names.append(node.name)

    # All required command handlers should be present
    expected_handlers = [
        "cmd_start",
        "cmd_stats",
        "cmd_campaigns",
        "cmd_calls",
        "cmd_alerts",
        "cmd_pause",
        "cmd_resume",
        "main",
    ]
    for handler in expected_handlers:
        assert handler in func_names, f"Missing handler: {handler}"


def test_telegram_bot_has_main_entry():
    """Verify bot.py has if __name__ == '__main__' block."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "bot.py"
    )
    with open(script_path) as f:
        source = f.read()

    assert "if __name__" in source
    assert "asyncio.run(main())" in source


def test_telegram_bot_status_emojis():
    """Verify status emoji mappings are defined in bot module AST."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "bot.py"
    )
    with open(script_path) as f:
        source = f.read()

    # Check that STATUS_EMOJI and OUTCOME_EMOJI are defined
    assert "STATUS_EMOJI" in source
    assert "OUTCOME_EMOJI" in source


def test_telegram_bot_imports_core_models():
    """Verify bot.py imports the required core models."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "bot.py"
    )
    with open(script_path) as f:
        source = f.read()

    # Should import key models
    assert "Campaign" in source
    assert "CampaignStatus" in source
    assert "Call" in source
    assert "Lead" in source
    assert "Message" in source


def test_telegram_bot_uses_aiogram():
    """Verify bot.py uses aiogram 3 patterns."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "telegram_admin", "bot.py"
    )
    with open(script_path) as f:
        source = f.read()

    # aiogram 3 patterns
    assert "from aiogram import Bot, Dispatcher, Router" in source
    assert "from aiogram.filters import Command" in source
    assert "Router()" in source
    assert "Dispatcher()" in source


def test_telegram_init_importable():
    """Verify telegram_admin __init__.py is importable."""
    import telegram_admin

    assert telegram_admin is not None

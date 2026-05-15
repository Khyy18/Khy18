import os
import tempfile
from unittest.mock import patch

import pytest
import pytest_asyncio

from kindergarten_accountant_bot.models.database import init_db


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Fixture that patches DB_PATH to a temp file and initializes the database."""
    db_file = str(tmp_path / "test.db")
    with patch("kindergarten_accountant_bot.config.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.database.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.employee.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.timesheet.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.child.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.payment.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.journal.DB_PATH", db_file), \
         patch("kindergarten_accountant_bot.models.reminder.DB_PATH", db_file):
        await init_db()
        yield db_file

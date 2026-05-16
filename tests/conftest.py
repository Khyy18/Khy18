from unittest.mock import patch

import pytest_asyncio

from kindergarten_accountant_bot.models.database import init_db


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Fixture that patches get_db_path to return a temp file and initializes the database."""
    db_file = str(tmp_path / "test.db")
    with patch("kindergarten_accountant_bot.config.get_db_path", return_value=db_file):
        await init_db()
        yield db_file

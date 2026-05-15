"""Tests for marketplace module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import marketplace
import database


@pytest.mark.asyncio
class TestMarketplace:
    """Tests for template marketplace."""

    async def test_init_marketplace_tables(self, initialized_db):
        """init_marketplace_tables creates tables without error."""
        await marketplace.init_marketplace_tables()

    async def test_get_categories(self):
        """get_categories returns list of category dicts."""
        categories = marketplace.get_categories()
        assert len(categories) == 4
        keys = {c["key"] for c in categories}
        assert "social_posts" in keys
        assert "email_templates" in keys
        assert "product_descriptions" in keys
        assert "proposals" in keys

    async def test_get_templates_by_category_empty(self, initialized_db):
        """get_templates_by_category returns empty for new category."""
        await marketplace.init_marketplace_tables()
        templates = await marketplace.get_templates_by_category("social_posts")
        assert templates == []

    async def test_purchase_template_not_found(self, initialized_db):
        """purchase_template returns False for nonexistent template."""
        await marketplace.init_marketplace_tables()
        result = await marketplace.purchase_template(12345, 999)
        assert result is False

    async def test_purchase_template_insufficient_balance(self, initialized_db):
        """purchase_template returns False when balance is insufficient."""
        await marketplace.init_marketplace_tables()
        import aiosqlite
        import config
        # Create a template manually
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO templates (category, title, preview, full_text, price)
                   VALUES (?, ?, ?, ?, ?)""",
                ("social_posts", "Test Template", "Preview...", "Full text", 100.0),
            )
            await db.commit()
            template_id = cursor.lastrowid

        await database.get_or_create_client(telegram_id=600, username="buyer")
        # Balance is 0, price is 100
        result = await marketplace.purchase_template(600, template_id)
        assert result is False

    async def test_purchase_template_success(self, initialized_db):
        """purchase_template succeeds with sufficient balance."""
        await marketplace.init_marketplace_tables()
        import aiosqlite
        import config
        # Create a template
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO templates (category, title, preview, full_text, price)
                   VALUES (?, ?, ?, ?, ?)""",
                ("email_templates", "Email Template", "Preview", "Full email", 50.0),
            )
            await db.commit()
            template_id = cursor.lastrowid

        await database.get_or_create_client(telegram_id=601, username="richbuyer")
        await database.update_balance(601, 200.0)

        result = await marketplace.purchase_template(601, template_id)
        assert result is True

        # Check balance was deducted
        balance = await database.get_client_balance(601)
        assert balance == 150.0

    async def test_categories_constant(self):
        """CATEGORIES constant has expected keys."""
        assert "social_posts" in marketplace.CATEGORIES
        assert "email_templates" in marketplace.CATEGORIES
        assert "product_descriptions" in marketplace.CATEGORIES
        assert "proposals" in marketplace.CATEGORIES

"""Tests for api/webhooks module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import aiosqlite

import config
import database


@pytest.mark.asyncio
class TestWebhooks:
    """Tests for B2B webhook system."""

    async def test_webhook_register(self, initialized_db):
        """Can register a webhook endpoint in database."""
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO webhook_endpoints (client_id, url, secret, active, created_at)
                   VALUES (?, ?, ?, 1, datetime('now'))""",
                (12345, "https://example.com/hook", "mysecret"),
            )
            await db.commit()
            webhook_id = cursor.lastrowid

        assert webhook_id is not None
        assert webhook_id > 0

    async def test_webhook_list(self, initialized_db):
        """Can list webhooks for a client."""
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                """INSERT INTO webhook_endpoints (client_id, url, secret, active, created_at)
                   VALUES (?, ?, ?, 1, datetime('now'))""",
                (500, "https://example.com/hook1", "sec1"),
            )
            await db.execute(
                """INSERT INTO webhook_endpoints (client_id, url, secret, active, created_at)
                   VALUES (?, ?, ?, 1, datetime('now'))""",
                (500, "https://example.com/hook2", "sec2"),
            )
            await db.commit()

            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM webhook_endpoints WHERE client_id = ? AND active = 1",
                (500,),
            )
            rows = await cursor.fetchall()

        assert len(rows) == 2

    async def test_webhook_delete(self, initialized_db):
        """Can deactivate a webhook."""
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO webhook_endpoints (client_id, url, secret, active, created_at)
                   VALUES (?, ?, ?, 1, datetime('now'))""",
                (600, "https://example.com/hookdel", "sec"),
            )
            await db.commit()
            webhook_id = cursor.lastrowid

            # Deactivate
            await db.execute(
                "UPDATE webhook_endpoints SET active = 0 WHERE id = ?",
                (webhook_id,),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT active FROM webhook_endpoints WHERE id = ?",
                (webhook_id,),
            )
            row = await cursor.fetchone()

        assert row[0] == 0

    async def test_webhook_delivery_record(self, initialized_db):
        """Can create webhook delivery records."""
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            # Create webhook first
            cursor = await db.execute(
                """INSERT INTO webhook_endpoints (client_id, url, secret, active, created_at)
                   VALUES (?, ?, ?, 1, datetime('now'))""",
                (700, "https://example.com/hookdel2", "sec"),
            )
            await db.commit()
            webhook_id = cursor.lastrowid

            # Create delivery record
            cursor = await db.execute(
                """INSERT INTO webhook_deliveries (webhook_id, order_id, status, attempts, last_attempt_at)
                   VALUES (?, ?, 'pending', 1, datetime('now'))""",
                (webhook_id, 1),
            )
            await db.commit()
            delivery_id = cursor.lastrowid

        assert delivery_id is not None
        assert delivery_id > 0

    async def test_webhook_hmac_signature(self, initialized_db):
        """HMAC signature generation works correctly."""
        import hmac
        import hashlib
        import json

        payload = json.dumps({"order_id": 1, "status": "completed"})
        secret = "test_secret"
        signature = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        assert len(signature) == 64  # SHA256 hex length
        # Verify it's deterministic
        sig2 = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == sig2

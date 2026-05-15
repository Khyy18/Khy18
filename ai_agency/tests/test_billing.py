"""Tests for billing module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database
import billing


@pytest.mark.asyncio
class TestBilling:
    """Test billing module with real SQLite."""

    async def test_check_balance_sufficient(self, sample_client):
        """check_balance returns True when balance is sufficient."""
        await database.update_balance(12345, 500.0)
        result = await billing.check_balance(12345, 100.0)
        assert result is True

    async def test_check_balance_insufficient(self, sample_client):
        """check_balance returns False when balance is insufficient."""
        await database.update_balance(12345, 50.0)
        result = await billing.check_balance(12345, 100.0)
        assert result is False

    async def test_charge_client_deducts_correctly(self, sample_client):
        """charge_client deducts the correct amount."""
        await database.update_balance(12345, 500.0)
        result = await billing.charge_client(12345, 200.0)
        assert result is True
        balance = await database.get_client_balance(12345)
        assert balance == 300.0

    async def test_charge_client_fails_insufficient(self, sample_client):
        """charge_client fails atomically with insufficient funds."""
        await database.update_balance(12345, 50.0)
        result = await billing.charge_client(12345, 100.0)
        assert result is False
        # Balance unchanged
        balance = await database.get_client_balance(12345)
        assert balance == 50.0

    async def test_top_up_balance(self, sample_client):
        """top_up_balance increases balance correctly."""
        await database.update_balance(12345, 100.0)
        new_balance = await billing.top_up_balance(12345, 200.0)
        assert new_balance == 300.0

    async def test_check_free_trial_new_user(self, sample_client):
        """check_free_trial returns True for new user."""
        result = await billing.check_free_trial(12345)
        assert result is True

    async def test_mark_free_trial_used(self, sample_client):
        """mark_free_trial_used makes trial unavailable."""
        await billing.mark_free_trial_used(12345)
        result = await billing.check_free_trial(12345)
        assert result is False

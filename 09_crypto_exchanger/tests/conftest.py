"""Common test fixtures for the crypto exchanger bot tests."""

import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import aiosqlite

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_currencies():
    """Sample currency list returned by API."""
    return [
        {
            "ticker": "btc",
            "name": "Bitcoin",
            "network": "btc",
            "isAvailable": True,
        },
        {
            "ticker": "eth",
            "name": "Ethereum",
            "network": "eth",
            "isAvailable": True,
        },
        {
            "ticker": "usdt",
            "name": "Tether",
            "network": "eth",
            "isAvailable": True,
        },
    ]


@pytest.fixture
def sample_estimate():
    """Sample estimate response from ChangeNOW."""
    return {
        "fromCurrency": "btc",
        "fromAmount": "1",
        "toCurrency": "eth",
        "toAmount": "15.5",
        "rateId": "rate-123-abc",
    }


@pytest.fixture
def sample_exchange():
    """Sample created exchange response from ChangeNOW."""
    return {
        "id": "exchange-abc-123",
        "payinAddress": "0xdeposit123",
        "payoutAddress": "0xpayout456",
        "fromCurrency": "btc",
        "toCurrency": "eth",
        "fromAmount": "1",
        "toAmount": "15.5",
        "status": "waiting",
    }


@pytest.fixture
def sample_status_response():
    """Sample status check response."""
    return {
        "id": "exchange-abc-123",
        "status": "finished",
        "payoutHash": "0xhash789",
    }


@pytest.fixture
def sample_exolix_estimate():
    """Sample estimate response from Exolix."""
    return {
        "coinFrom": "BTC",
        "coinTo": "ETH",
        "amount": 1.0,
        "toAmount": 15.3,
        "rate": 15.3,
    }


@pytest.fixture
def sample_exolix_exchange():
    """Sample created exchange response from Exolix."""
    return {
        "id": 12345,
        "depositAddress": "0xexolixdeposit",
        "coinFrom": "BTC",
        "coinTo": "ETH",
        "amount": 1.0,
        "status": "wait",
    }


@pytest.fixture
def sample_exolix_status():
    """Sample Exolix status response."""
    return {
        "id": 12345,
        "status": "success",
        "hashOut": {"hash": "0xexolixhash"},
    }


@pytest.fixture
async def test_db(tmp_path):
    """Provide an in-memory aiosqlite database with schema initialized."""
    from db.models import SCHEMA

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    await db.commit()
    yield db
    await db.close()


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp ClientSession with configurable responses."""

    class MockResponse:
        def __init__(self, json_data, status=200):
            self._json_data = json_data
            self.status = status

        async def json(self):
            return self._json_data

        async def text(self):
            import json
            return json.dumps(self._json_data)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockSession:
        def __init__(self):
            self.responses = []
            self._call_index = 0

        def add_response(self, json_data, status=200):
            self.responses.append(MockResponse(json_data, status))

        def request(self, method, url, **kwargs):
            if self._call_index < len(self.responses):
                resp = self.responses[self._call_index]
                self._call_index += 1
                return resp
            return MockResponse({"error": "no more responses"}, 500)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    return MockSession

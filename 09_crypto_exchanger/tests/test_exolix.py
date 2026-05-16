"""Tests for Exolix API client."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import aiohttp


@pytest.fixture
def mock_exolix_session():
    """Provide a patched aiohttp session for Exolix tests."""

    def _make_session(json_data, status=200):
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=json_data)
        mock_resp.text = AsyncMock(return_value=str(json_data))
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.request = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        return mock_session

    return _make_session


@pytest.mark.asyncio
async def test_get_currencies_with_data_wrapper(mock_exolix_session):
    """Test get_currencies handles the {data: [...]} response format."""
    currencies = [
        {"code": "BTC", "name": "Bitcoin"},
        {"code": "ETH", "name": "Ethereum"},
    ]
    session = mock_exolix_session({"data": currencies})

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import get_currencies

        result = await get_currencies()

    assert result == currencies
    assert len(result) == 2
    assert result[0]["code"] == "BTC"


@pytest.mark.asyncio
async def test_get_currencies_with_list_response(mock_exolix_session):
    """Test get_currencies handles a direct list response."""
    currencies = [{"code": "BTC", "name": "Bitcoin"}]
    session = mock_exolix_session(currencies)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import get_currencies

        result = await get_currencies()

    assert result == currencies


@pytest.mark.asyncio
async def test_get_estimated_amount(sample_exolix_estimate, mock_exolix_session):
    """Test get_estimated_amount returns rate data with correct params."""
    session = mock_exolix_session(sample_exolix_estimate)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import get_estimated_amount

        result = await get_estimated_amount("btc", "eth", 1.0, "fixed")

    assert result["toAmount"] == 15.3
    call_args = session.request.call_args
    assert call_args[0][0] == "GET"
    assert "/rate" in call_args[0][1]
    params = call_args[1].get("params", {})
    assert params["coinFrom"] == "BTC"
    assert params["coinTo"] == "ETH"
    assert params["rateType"] == "fixed"


@pytest.mark.asyncio
async def test_get_estimated_amount_float_rate(sample_exolix_estimate, mock_exolix_session):
    """Test get_estimated_amount with float rate type."""
    session = mock_exolix_session(sample_exolix_estimate)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import get_estimated_amount

        result = await get_estimated_amount("btc", "eth", 1.0, "float")

    call_args = session.request.call_args
    params = call_args[1].get("params", {})
    assert params["rateType"] == "float"


@pytest.mark.asyncio
async def test_create_exchange(sample_exolix_exchange, mock_exolix_session):
    """Test create_exchange sends correct body and returns exchange data."""
    session = mock_exolix_session(sample_exolix_exchange, status=201)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import create_exchange

        result = await create_exchange("btc", "eth", 1.0, "0xwallet123", "fixed")

    assert result["id"] == 12345
    assert result["depositAddress"] == "0xexolixdeposit"
    call_args = session.request.call_args
    assert call_args[0][0] == "POST"
    assert "/transactions" in call_args[0][1]
    body = call_args[1].get("json", {})
    assert body["coinFrom"] == "BTC"
    assert body["coinTo"] == "ETH"
    assert body["withdrawalAddress"] == "0xwallet123"


@pytest.mark.asyncio
async def test_get_exchange_status(sample_exolix_status, mock_exolix_session):
    """Test get_exchange_status returns status data."""
    session = mock_exolix_session(sample_exolix_status)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import get_exchange_status

        result = await get_exchange_status("12345")

    assert result["status"] == "success"
    assert result["hashOut"]["hash"] == "0xexolixhash"
    call_args = session.request.call_args
    assert "/transactions/12345" in call_args[0][1]


@pytest.mark.asyncio
async def test_api_error_raises_exolix_error(mock_exolix_session):
    """Test that non-200/201 status raises ExolixError."""
    session = mock_exolix_session({"message": "Unauthorized"}, status=401)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.exolix import get_currencies, ExolixError

        with pytest.raises(ExolixError) as exc_info:
            await get_currencies()
        assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_connection_error_raises_exolix_error():
    """Test that connection errors are wrapped in ExolixError."""
    mock_session = AsyncMock()
    mock_session.request = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from services.exolix import get_currencies, ExolixError

        with pytest.raises(ExolixError) as exc_info:
            await get_currencies()
        assert "Connection error" in str(exc_info.value)

"""Tests for ChangeNOW API client."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import aiohttp


@pytest.fixture
def mock_changenow_session(sample_currencies, sample_estimate, sample_exchange, sample_status_response):
    """Provide a patched aiohttp session for ChangeNOW tests."""

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
async def test_get_currencies(sample_currencies, mock_changenow_session):
    """Test that get_currencies returns a list of currencies from the API."""
    session = mock_changenow_session(sample_currencies)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import get_currencies

        result = await get_currencies()

    assert result == sample_currencies
    assert len(result) == 3
    assert result[0]["ticker"] == "btc"


@pytest.mark.asyncio
async def test_get_estimated_amount_standard(sample_estimate, mock_changenow_session):
    """Test get_estimated_amount with standard flow returns estimate data."""
    session = mock_changenow_session(sample_estimate)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import get_estimated_amount

        result = await get_estimated_amount("btc", "eth", 1.0, "standard")

    assert result["toAmount"] == "15.5"
    assert result["fromCurrency"] == "btc"
    # Verify the request was made with correct params
    session.request.assert_called_once()
    call_args = session.request.call_args
    assert call_args[0][0] == "GET"
    assert "/exchange/estimated-amount" in call_args[0][1]


@pytest.mark.asyncio
async def test_get_estimated_amount_fixed_rate(sample_estimate, mock_changenow_session):
    """Test get_estimated_amount with fixed-rate flow includes flow param."""
    session = mock_changenow_session(sample_estimate)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import get_estimated_amount

        result = await get_estimated_amount("btc", "eth", 1.0, "fixed-rate")

    assert result["rateId"] == "rate-123-abc"
    call_args = session.request.call_args
    params = call_args[1].get("params", call_args[0][2] if len(call_args[0]) > 2 else {})
    # Check flow was passed in params
    assert "fixed-rate" in str(call_args)


@pytest.mark.asyncio
async def test_create_exchange_standard(sample_exchange, mock_changenow_session):
    """Test create_exchange with standard flow."""
    session = mock_changenow_session(sample_exchange)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import create_exchange

        result = await create_exchange("btc", "eth", 1.0, "0xpayout456")

    assert result["id"] == "exchange-abc-123"
    assert result["payinAddress"] == "0xdeposit123"
    assert result["status"] == "waiting"
    # Verify POST was used
    call_args = session.request.call_args
    assert call_args[0][0] == "POST"


@pytest.mark.asyncio
async def test_create_exchange_fixed_rate(sample_exchange, mock_changenow_session):
    """Test create_exchange with fixed-rate flow includes rateId."""
    session = mock_changenow_session(sample_exchange)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import create_exchange

        result = await create_exchange(
            "btc", "eth", 1.0, "0xpayout456",
            flow="fixed-rate", rate_id="rate-123-abc"
        )

    assert result["id"] == "exchange-abc-123"
    call_args = session.request.call_args
    body = call_args[1].get("json", {})
    assert body.get("rateId") == "rate-123-abc"
    assert body.get("flow") == "fixed-rate"


@pytest.mark.asyncio
async def test_get_exchange_status(sample_status_response, mock_changenow_session):
    """Test get_exchange_status returns status data."""
    session = mock_changenow_session(sample_status_response)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import get_exchange_status

        result = await get_exchange_status("exchange-abc-123")

    assert result["status"] == "finished"
    assert result["payoutHash"] == "0xhash789"
    call_args = session.request.call_args
    assert "exchange-abc-123" in call_args[0][1]


@pytest.mark.asyncio
async def test_api_error_raises_changenow_error(mock_changenow_session):
    """Test that non-200 status code raises ChangeNowError."""
    session = mock_changenow_session({"error": "not found"}, status=404)

    with patch("aiohttp.ClientSession", return_value=session):
        from services.changenow import get_currencies, ChangeNowError

        with pytest.raises(ChangeNowError) as exc_info:
            await get_currencies()
        assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_connection_error_raises_changenow_error():
    """Test that connection errors are wrapped in ChangeNowError."""
    mock_session = AsyncMock()
    mock_session.request = MagicMock(side_effect=aiohttp.ClientError("timeout"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from services.changenow import get_currencies, ChangeNowError

        with pytest.raises(ChangeNowError) as exc_info:
            await get_currencies()
        assert "Connection error" in str(exc_info.value)

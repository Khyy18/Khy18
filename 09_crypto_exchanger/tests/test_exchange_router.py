"""Tests for exchange router with fallback logic."""

import pytest
from unittest.mock import patch, AsyncMock

from services.changenow import ChangeNowError
from services.exolix import ExolixError


@pytest.fixture(autouse=True)
def clear_rate_cache():
    """Clear rate cache before each test."""
    from services.rate_cache import rate_cache
    rate_cache.clear()
    yield
    rate_cache.clear()


@pytest.mark.asyncio
async def test_get_estimate_primary_provider_success():
    """Test that estimate uses ChangeNOW (primary) when it succeeds."""
    cn_response = {"toAmount": "15.0", "rateId": "rate-abc"}

    with patch("services.changenow.get_estimated_amount", new_callable=AsyncMock) as mock_cn:
        mock_cn.return_value = cn_response
        from services.exchange_router import get_estimate

        result = await get_estimate("btc", "eth", 1.0, "standard")

    assert result["provider"] == "changenow"
    # Markup of 1.5% applied: 15.0 - (15.0 * 0.015) = 14.775
    assert abs(result["toAmount"] - 14.775) < 0.001
    assert result["rawAmount"] == 15.0
    assert abs(result["markupAmount"] - 0.225) < 0.001
    assert result["rateId"] == "rate-abc"


@pytest.mark.asyncio
async def test_get_estimate_fallback_to_exolix():
    """Test that estimate falls back to Exolix when ChangeNOW fails."""
    exolix_response = {"toAmount": 14.5}

    with patch("services.changenow.get_estimated_amount", new_callable=AsyncMock) as mock_cn, \
         patch("services.exolix.get_estimated_amount", new_callable=AsyncMock) as mock_ex:
        mock_cn.side_effect = ChangeNowError("API down")
        mock_ex.return_value = exolix_response
        from services.exchange_router import get_estimate

        result = await get_estimate("btc", "eth", 1.0, "standard")

    assert result["provider"] == "exolix"
    # Markup of 1.5% applied: 14.5 - (14.5 * 0.015) = 14.2825
    assert abs(result["toAmount"] - 14.2825) < 0.001
    assert result["rawAmount"] == 14.5


@pytest.mark.asyncio
async def test_get_estimate_both_providers_fail():
    """Test that proper error is raised when both providers fail."""
    with patch("services.changenow.get_estimated_amount", new_callable=AsyncMock) as mock_cn, \
         patch("services.exolix.get_estimated_amount", new_callable=AsyncMock) as mock_ex:
        mock_cn.side_effect = ChangeNowError("API down")
        mock_ex.side_effect = ExolixError("Also down")
        from services.exchange_router import get_estimate

        with pytest.raises(ExolixError):
            await get_estimate("btc", "eth", 1.0, "standard")


@pytest.mark.asyncio
async def test_get_currencies_primary_success():
    """Test get_currencies returns data from ChangeNOW when available."""
    currencies = [{"ticker": "btc"}, {"ticker": "eth"}]

    with patch("services.changenow.get_currencies", new_callable=AsyncMock) as mock_cn:
        mock_cn.return_value = currencies
        from services.exchange_router import get_currencies

        result = await get_currencies()

    assert result == currencies


@pytest.mark.asyncio
async def test_get_currencies_fallback_to_exolix():
    """Test get_currencies falls back to Exolix on ChangeNOW failure."""
    exolix_currencies = [{"code": "BTC"}, {"code": "ETH"}]

    with patch("services.changenow.get_currencies", new_callable=AsyncMock) as mock_cn, \
         patch("services.exolix.get_currencies", new_callable=AsyncMock) as mock_ex:
        mock_cn.side_effect = ChangeNowError("down")
        mock_ex.return_value = exolix_currencies
        from services.exchange_router import get_currencies

        result = await get_currencies()

    assert result == exolix_currencies


@pytest.mark.asyncio
async def test_create_exchange_primary_success():
    """Test create_exchange uses ChangeNOW when it succeeds."""
    cn_response = {
        "id": "cn-exchange-1",
        "payinAddress": "0xdeposit",
        "status": "waiting",
    }

    with patch("services.changenow.create_exchange", new_callable=AsyncMock) as mock_cn:
        mock_cn.return_value = cn_response
        from services.exchange_router import create_exchange

        result = await create_exchange("btc", "eth", 1.0, "0xwallet")

    assert result["provider"] == "changenow"
    assert result["id"] == "cn-exchange-1"
    assert result["depositAddress"] == "0xdeposit"


@pytest.mark.asyncio
async def test_create_exchange_fallback_to_exolix():
    """Test create_exchange falls back to Exolix on ChangeNOW failure."""
    ex_response = {
        "id": 99999,
        "depositAddress": "0xexdeposit",
        "status": "wait",
    }

    with patch("services.changenow.create_exchange", new_callable=AsyncMock) as mock_cn, \
         patch("services.exolix.create_exchange", new_callable=AsyncMock) as mock_ex:
        mock_cn.side_effect = ChangeNowError("failed")
        mock_ex.return_value = ex_response
        from services.exchange_router import create_exchange

        result = await create_exchange("btc", "eth", 1.0, "0xwallet")

    assert result["provider"] == "exolix"
    assert result["id"] == "99999"
    assert result["depositAddress"] == "0xexdeposit"


@pytest.mark.asyncio
async def test_create_exchange_both_fail():
    """Test create_exchange raises when both providers fail."""
    with patch("services.changenow.create_exchange", new_callable=AsyncMock) as mock_cn, \
         patch("services.exolix.create_exchange", new_callable=AsyncMock) as mock_ex:
        mock_cn.side_effect = ChangeNowError("cn down")
        mock_ex.side_effect = ExolixError("ex down")
        from services.exchange_router import create_exchange

        with pytest.raises(ExolixError):
            await create_exchange("btc", "eth", 1.0, "0xwallet")


@pytest.mark.asyncio
async def test_get_status_changenow():
    """Test get_status calls ChangeNOW for changenow provider."""
    cn_response = {"status": "finished", "payoutHash": "0xhash"}

    with patch("services.changenow.get_exchange_status", new_callable=AsyncMock) as mock_cn:
        mock_cn.return_value = cn_response
        from services.exchange_router import get_status

        result = await get_status("exchange-1", "changenow")

    assert result["status"] == "finished"
    assert result["hash"] == "0xhash"


@pytest.mark.asyncio
async def test_get_status_exolix_normalizes_status():
    """Test get_status normalizes Exolix statuses."""
    ex_response = {"status": "success", "hashOut": {"hash": "0xouthash"}}

    with patch("services.exolix.get_exchange_status", new_callable=AsyncMock) as mock_ex:
        mock_ex.return_value = ex_response
        from services.exchange_router import get_status

        result = await get_status("12345", "exolix")

    # "success" should be normalized to "finished"
    assert result["status"] == "finished"
    assert result["hash"] == "0xouthash"


@pytest.mark.asyncio
async def test_get_estimate_uses_cache():
    """Test that repeated calls use cache instead of making API calls."""
    cn_response = {"toAmount": "10.0"}

    with patch("services.changenow.get_estimated_amount", new_callable=AsyncMock) as mock_cn:
        mock_cn.return_value = cn_response
        from services.exchange_router import get_estimate

        result1 = await get_estimate("btc", "eth", 1.0, "standard")
        result2 = await get_estimate("btc", "eth", 1.0, "standard")

    # Should only call API once due to caching
    mock_cn.assert_called_once()
    assert result1 == result2


@pytest.mark.asyncio
async def test_markup_applied_correctly():
    """Test that markup percentage is applied to reduce user's received amount."""
    from services.exchange_router import _apply_markup

    # With default 1.5% markup, 100 becomes 98.5 for user
    final, markup = _apply_markup(100.0)
    assert final == 98.5
    assert markup == 1.5

    # Edge case: zero amount
    final, markup = _apply_markup(0.0)
    assert final == 0.0
    assert markup == 0.0

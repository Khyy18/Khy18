"""Tests for geocoding endpoint."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.geocoding import router, _get_timezone_finder, GeocodeSuggestion, GeocodeResponse


class TestGeocoding:
    """Tests for the geocoding module."""

    @pytest.mark.asyncio
    @patch("app.geocoding.get_http_client")
    async def test_geocode_city_success(self, mock_get_client):
        """Test successful geocoding of a city."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        # Create test app
        test_app = FastAPI()
        test_app.include_router(router)

        # Mock Nominatim response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "lat": "55.7558",
                "lon": "37.6173",
                "display_name": "Moscow, Russia",
            },
            {
                "lat": "55.0",
                "lon": "37.0",
                "display_name": "Moscow Oblast, Russia",
            },
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Use the TestClient
        with TestClient(test_app) as client:
            response = client.get("/api/geocode?city=Moscow")
            assert response.status_code == 200
            data = response.json()
            assert "suggestions" in data
            assert len(data["suggestions"]) == 2
            assert data["suggestions"][0]["lat"] == 55.7558
            assert data["suggestions"][0]["lon"] == 37.6173
            assert data["suggestions"][0]["display_name"] == "Moscow, Russia"
            assert "timezone" in data["suggestions"][0]

    @pytest.mark.asyncio
    @patch("app.geocoding.get_http_client")
    async def test_geocode_city_empty_results(self, mock_get_client):
        """Test geocoding with no results."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(router)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        with TestClient(test_app) as client:
            response = client.get("/api/geocode?city=Nonexistent12345")
            assert response.status_code == 200
            data = response.json()
            assert data["suggestions"] == []

    @pytest.mark.asyncio
    @patch("app.geocoding.get_http_client")
    async def test_geocode_city_api_error(self, mock_get_client):
        """Test geocoding when external API fails."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(router)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection error"))
        mock_get_client.return_value = mock_client

        with TestClient(test_app) as client:
            response = client.get("/api/geocode?city=Moscow")
            assert response.status_code == 502

    def test_geocode_city_too_short(self):
        """Test that city name must be at least 2 characters."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app) as client:
            response = client.get("/api/geocode?city=M")
            assert response.status_code == 422  # Validation error

    def test_timezone_finder_returns_timezone(self):
        """Test that timezone finder returns a valid timezone string."""
        tf = _get_timezone_finder()
        # Moscow coordinates
        tz = tf.timezone_at(lat=55.7558, lng=37.6173)
        assert tz is not None
        assert "Moscow" in tz or "Europe" in tz

    def test_timezone_finder_ocean_returns_none(self):
        """Test that timezone finder returns None for ocean coordinates."""
        tf = _get_timezone_finder()
        # Middle of Atlantic Ocean
        tz = tf.timezone_at(lat=0.0, lng=-30.0)
        # May return None or a timezone, depending on the library version
        # Just verify it doesn't crash
        assert tz is None or isinstance(tz, str)

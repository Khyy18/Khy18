"""Tests for OCR endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app import create_app

AUTH_HEADERS = {"Authorization": "Bearer change-me-in-production"}


@pytest_asyncio.fixture
async def client():
    """Create async test client."""
    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_ocr_process_success(client):
    """Test OCR process endpoint with mocked Groq response."""
    mock_response = json.dumps({
        "doc_type": "invoice",
        "fields": {
            "\u041d\u043e\u043c\u0435\u0440": "123",
            "\u0414\u0430\u0442\u0430": "01.01.2024",
            "\u0421\u0443\u043c\u043c\u0430": "50000.00",
            "\u0418\u041d\u041d": "7707083893",
        },
    })

    with patch("backend.routers.ocr.vision_completion", new_callable=AsyncMock) as mock_vision:
        mock_vision.return_value = mock_response
        response = await client.post(
            "/api/v1/ocr/process",
            json={"image_base64": "aGVsbG8=", "filename": "test.jpg"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["doc_type"] == "invoice"
    assert "\u041d\u043e\u043c\u0435\u0440" in data["fields"]
    assert data["fields"]["\u0418\u041d\u041d"] == "7707083893"


@pytest.mark.asyncio
async def test_ocr_process_invalid_image(client):
    """Test OCR process with empty image_base64."""
    response = await client.post(
        "/api/v1/ocr/process",
        json={"image_base64": "", "filename": "test.jpg"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_ocr_process_ai_unavailable(client):
    """Test OCR process when AI service returns None."""
    with patch("backend.routers.ocr.vision_completion", new_callable=AsyncMock) as mock_vision:
        mock_vision.return_value = None
        response = await client.post(
            "/api/v1/ocr/process",
            json={"image_base64": "aGVsbG8=", "filename": "test.jpg"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_ocr_process_unparseable_response(client):
    """Test OCR process when AI returns non-JSON text."""
    with patch("backend.routers.ocr.vision_completion", new_callable=AsyncMock) as mock_vision:
        mock_vision.return_value = "This is not valid JSON text about a document"
        response = await client.post(
            "/api/v1/ocr/process",
            json={"image_base64": "aGVsbG8=", "filename": "test.jpg"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["doc_type"] == "unknown"
    assert data["fields"] == {}
    assert "not valid JSON" in data["raw_text"]


@pytest.mark.asyncio
async def test_ocr_to_excel_success(client):
    """Test Excel generation from structured OCR data."""
    response = await client.post(
        "/api/v1/ocr/to-excel",
        json={
            "doc_type": "invoice",
            "fields": {
                "\u041d\u043e\u043c\u0435\u0440": "123",
                "\u0414\u0430\u0442\u0430": "01.01.2024",
                "\u0421\u0443\u043c\u043c\u0430": "50000.00",
            },
            "title": "\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_ocr_to_excel_empty(client):
    """Test Excel generation with empty fields dict."""
    response = await client.post(
        "/api/v1/ocr/to-excel",
        json={
            "doc_type": "unknown",
            "fields": {},
            "title": "\u041f\u0443\u0441\u0442\u043e\u0439",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_ocr_process_no_auth(client):
    """Test OCR process endpoint without auth token."""
    response = await client.post(
        "/api/v1/ocr/process",
        json={"image_base64": "aGVsbG8=", "filename": "test.jpg"},
    )
    assert response.status_code == 401

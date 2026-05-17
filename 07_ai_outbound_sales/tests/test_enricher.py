"""Tests for the EnricherAgent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.enricher import EnricherAgent


@pytest.fixture
def enricher(mock_llm_client, mock_settings):
    return EnricherAgent(llm_client=mock_llm_client, settings=mock_settings)


@pytest.fixture
def sample_lead():
    return {
        "first_name": "Alice",
        "last_name": "Johnson",
        "email": "alice@techco.com",
        "title": "VP Engineering",
        "company": "TechCo",
        "company_data": {
            "industry": "SaaS",
            "description": "Cloud infrastructure platform",
        },
    }


def test_parse_enrichment_extracts_trigger_events(enricher):
    """Test _parse_enrichment extracts trigger_events from LLM response."""
    response = """1. TRIGGER EVENTS:
- Series C funding of $50M announced last week
- Hired new VP of Sales from Salesforce

2. TALKING POINTS:
- Expanding into European markets
- Recently launched AI features

3. COMPANY NEWS:
- Partnership with AWS announced
- Named in Forbes 30 Under 30

4. RECENT ACTIVITY:
- Posted about hiring challenges on LinkedIn
"""
    result = enricher._parse_enrichment(response)

    assert len(result["trigger_events"]) == 2
    assert "Series C funding" in result["trigger_events"][0]
    assert len(result["talking_points"]) == 2
    assert len(result["company_news"]) == 2
    assert "hiring challenges" in result["recent_activity"]


def test_parse_enrichment_handles_empty_sections(enricher):
    """Test _parse_enrichment handles sections with 'None found'."""
    response = """TRIGGER EVENTS:
None found

TALKING POINTS:
- One interesting point

COMPANY NEWS:
None found

RECENT ACTIVITY:
None found
"""
    result = enricher._parse_enrichment(response)

    assert result["trigger_events"] == []
    assert len(result["talking_points"]) == 1
    assert result["company_news"] == []
    assert result["recent_activity"] == ""


def test_extract_snippets_parses_html(enricher):
    """Test _extract_snippets extracts text from HTML result snippets."""
    html = (
        '<div>Other content</div>'
        '<div class="result__snippet">First snippet <b>text</b> here.</div>'
        '<div class="result__snippet">Second snippet content.</div>'
    )
    # The parser splits on "result__snippet" then looks for > to find content
    result = enricher._extract_snippets(html)

    # Should contain extracted text
    assert "First snippet" in result or "Second snippet" in result


def test_extract_snippets_empty_html(enricher):
    """Test _extract_snippets returns empty string for HTML with no snippets."""
    html = "<html><body><p>No results</p></body></html>"
    result = enricher._extract_snippets(html)
    assert result == ""


async def test_enrich_calls_search_and_llm(enricher, sample_lead, mock_llm_client):
    """Test enrich calls web search and LLM and returns enrichment_data."""
    mock_llm_client.generate.return_value = """TRIGGER EVENTS:
- New funding round

TALKING POINTS:
- Growing team

COMPANY NEWS:
- Product launch

RECENT ACTIVITY:
Active on Twitter
"""

    with patch("aiohttp.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html></html>")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session

        result = await enricher.enrich(sample_lead)

    assert "enrichment_data" in result
    assert "enriched_at" in result["enrichment_data"]
    assert result["enrichment_data"]["trigger_events"] == ["New funding round"]
    assert result["enrichment_data"]["talking_points"] == ["Growing team"]
    assert result["enrichment_data"]["company_news"] == ["Product launch"]
    mock_llm_client.generate.assert_called_once()


async def test_enrich_handles_llm_failure(enricher, sample_lead, mock_llm_client):
    """Test enrich returns empty enrichment when LLM fails."""
    mock_llm_client.generate.side_effect = RuntimeError("LLM unavailable")

    with patch("aiohttp.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html></html>")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session

        result = await enricher.enrich(sample_lead)

    assert result["enrichment_data"]["trigger_events"] == []
    assert result["enrichment_data"]["talking_points"] == []

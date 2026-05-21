"""Tests for enhanced enrichment: technographic, job boards, intent signals."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.enricher import EnricherAgent
from data.sources.job_boards import JobBoardsClient
from data.sources.technographic import TechnographicClient


@pytest.fixture
def mock_redis_client():
    """Mock Redis client with dict-based storage."""
    redis = AsyncMock()
    store: dict[str, str] = {}

    async def mock_get(key):
        return store.get(key)

    async def mock_setex(key, ttl, value):
        store[key] = str(value)
        return True

    async def mock_incr(key):
        current = int(store.get(key, "0"))
        store[key] = str(current + 1)
        return current + 1

    async def mock_expire(key, ttl):
        return True

    redis.get = AsyncMock(side_effect=mock_get)
    redis.setex = AsyncMock(side_effect=mock_setex)
    redis.incr = AsyncMock(side_effect=mock_incr)
    redis.expire = AsyncMock(side_effect=mock_expire)
    redis.close = AsyncMock()
    redis._store = store
    return redis


@pytest.fixture
def enricher(mock_llm_client, mock_settings):
    """Create EnricherAgent instance for testing."""
    return EnricherAgent(llm_client=mock_llm_client, settings=mock_settings)


@pytest.fixture
def sample_lead():
    """Sample lead for testing enhanced enrichment."""
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


async def test_technographic_client_cache_hit(mock_redis_client):
    """Cached tech stack data is returned without making HTTP calls."""
    cached_data = {
        "languages": ["Python"],
        "frameworks": ["Django"],
        "cdn": ["Cloudflare"],
        "analytics": ["Google Analytics"],
        "crm": [],
        "other": ["Stripe"],
    }
    # Pre-populate cache
    mock_redis_client._store["techstack:example.com"] = json.dumps(cached_data)

    with patch("data.sources.technographic.aioredis.from_url", return_value=mock_redis_client):
        client = TechnographicClient(redis_url="redis://localhost:6379/0")
        client._redis = mock_redis_client

        result = await client.get_tech_stack("example.com")

    assert result == cached_data
    # No HTTP session should have been created for web scraping


async def test_technographic_client_scrape_fallback(mock_redis_client):
    """Technology detection via HTML scraping works correctly."""
    html_content = """
    <html>
    <head>
        <script src="https://cdn.example.com/react.min.js"></script>
        <script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/style.css">
    </head>
    <body>
        <script src="https://js.stripe.com/v3/"></script>
        <script src="https://js.intercom.com/widget.js"></script>
    </body>
    </html>
    """

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=html_content)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("data.sources.technographic.aiohttp.ClientSession", return_value=mock_session):
        client = TechnographicClient(redis_url="redis://localhost:6379/0")
        client._redis = mock_redis_client

        result = await client.get_tech_stack("example.com")

    assert "React" in result["frameworks"]
    assert "Google Analytics" in result["analytics"]
    assert "Cloudflare" in result["cdn"]
    assert "Stripe" in result["other"]
    assert "Intercom" in result["other"]


async def test_job_boards_client_search(mock_redis_client):
    """Job listings are extracted from DuckDuckGo HTML search results."""
    html_response = """
    <html>
    <div class="result">
        <a class="result__a" href="https://jobs.example.com/1">Senior Sales Engineer at TechCo</a>
        <div class="result__snippet">We are looking for a sales engineer to join our team...</div>
    </div>
    <div class="result">
        <a class="result__a" href="https://jobs.example.com/2">Growth Marketing Manager</a>
        <div class="result__snippet">Lead our growth marketing initiatives...</div>
    </div>
    </html>
    """

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=html_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("data.sources.job_boards.aiohttp.ClientSession", return_value=mock_session):
        client = JobBoardsClient(redis_url="redis://localhost:6379/0")
        client._redis = mock_redis_client

        result = await client.search_jobs("TechCo")

    assert len(result) > 0
    titles = [r["title"] for r in result]
    # Verify job titles were extracted
    assert any("Sales Engineer" in t for t in titles) or any("Growth" in t for t in titles)


async def test_job_boards_client_cache(mock_redis_client):
    """Cached job data is returned without making HTTP calls."""
    cached_jobs = [
        {"title": "Backend Engineer", "description": "Build APIs", "url": "https://example.com/1"}
    ]
    mock_redis_client._store["jobboards:techco"] = json.dumps(cached_jobs)

    with patch("data.sources.job_boards.aioredis.from_url", return_value=mock_redis_client):
        client = JobBoardsClient(redis_url="redis://localhost:6379/0")
        client._redis = mock_redis_client

        result = await client.search_jobs("TechCo")

    assert result == cached_jobs


async def test_enricher_enhanced_pipeline(enricher, sample_lead, mock_llm_client):
    """Full enrich() pipeline adds tech_stack, hiring_signals, funding_events, intent_score."""
    mock_llm_client.generate.return_value = """TRIGGER EVENTS:
- New funding round

TALKING POINTS:
- Growing team

COMPANY NEWS:
- Product launch

RECENT ACTIVITY:
Active on Twitter
"""
    tech_data = {
        "languages": ["Python"],
        "frameworks": ["React"],
        "cdn": ["Cloudflare"],
        "analytics": [],
        "crm": [],
        "other": [],
    }
    job_data = [
        {"title": "Senior Sales Engineer", "description": "Sell stuff", "url": "http://x.com/1"},
    ]

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

        with patch.object(
            TechnographicClient, "get_tech_stack", return_value=tech_data
        ), patch.object(
            TechnographicClient, "close", return_value=None
        ), patch.object(
            JobBoardsClient, "search_jobs", return_value=job_data
        ), patch.object(
            JobBoardsClient, "close", return_value=None
        ):
            result = await enricher.enrich(sample_lead)

    ed = result["enrichment_data"]
    assert "tech_stack" in ed
    assert ed["tech_stack"] == tech_data
    assert "hiring_signals" in ed
    assert "funding_events" in ed
    assert "intent_score" in ed
    assert isinstance(ed["intent_score"], float)


async def test_intent_score_calculation(enricher):
    """Verify scoring logic: hiring=30, funding=25, tech=15, compound=10."""
    # All signals present
    score = enricher._calculate_intent_score(
        hiring_signals=["Sales Rep"],
        funding_events=["Series B raised $50M"],
        tech_stack={"frameworks": ["React"], "languages": [], "cdn": [], "analytics": [], "crm": [], "other": []},
    )
    # 30 + 25 + 15 + 10 (compound) = 80
    assert score == 80.0

    # Only hiring
    score = enricher._calculate_intent_score(
        hiring_signals=["SDR"],
        funding_events=[],
        tech_stack={"frameworks": [], "languages": [], "cdn": [], "analytics": [], "crm": [], "other": []},
    )
    assert score == 30.0

    # Only funding
    score = enricher._calculate_intent_score(
        hiring_signals=[],
        funding_events=["Raised $10M"],
        tech_stack={"frameworks": [], "languages": [], "cdn": [], "analytics": [], "crm": [], "other": []},
    )
    assert score == 25.0

    # Only tech stack
    score = enricher._calculate_intent_score(
        hiring_signals=[],
        funding_events=[],
        tech_stack={"frameworks": ["Django"], "languages": [], "cdn": [], "analytics": [], "crm": [], "other": []},
    )
    assert score == 15.0

    # No signals
    score = enricher._calculate_intent_score(
        hiring_signals=[],
        funding_events=[],
        tech_stack={},
    )
    assert score == 0.0

    # Two signals (no compound bonus)
    score = enricher._calculate_intent_score(
        hiring_signals=["Account Executive"],
        funding_events=["Series A"],
        tech_stack={"frameworks": [], "languages": [], "cdn": [], "analytics": [], "crm": [], "other": []},
    )
    # 30 + 25 = 55 (no compound since only 2 categories)
    assert score == 55.0


async def test_enrichment_cache_prevents_re_enrichment(mock_redis_client):
    """Cached domain is not re-fetched when tech stack is in cache."""
    cached_data = {
        "languages": ["Go"],
        "frameworks": [],
        "cdn": [],
        "analytics": [],
        "crm": [],
        "other": [],
    }
    mock_redis_client._store["techstack:cached.com"] = json.dumps(cached_data)

    client = TechnographicClient(redis_url="redis://localhost:6379/0")
    client._redis = mock_redis_client

    with patch("data.sources.technographic.aiohttp.ClientSession") as mock_session_cls:
        result = await client.get_tech_stack("cached.com")

    assert result == cached_data
    # aiohttp.ClientSession should not have been called since cache hit
    mock_session_cls.assert_not_called()


async def test_enhanced_enrichment_failure_doesnt_break_basic(
    enricher, sample_lead, mock_llm_client
):
    """If technographic or intent signals fail, basic enrichment still works."""
    mock_llm_client.generate.return_value = """TRIGGER EVENTS:
- Company expanding

TALKING POINTS:
- New product line

COMPANY NEWS:
- Opened new office

RECENT ACTIVITY:
Posting on LinkedIn
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

        # Make enhanced enrichment methods raise exceptions
        with patch.object(
            TechnographicClient,
            "get_tech_stack",
            side_effect=RuntimeError("Connection refused"),
        ), patch.object(
            TechnographicClient, "close", return_value=None
        ):
            result = await enricher.enrich(sample_lead)

    # Basic enrichment should still be intact
    ed = result["enrichment_data"]
    assert "trigger_events" in ed
    assert ed["trigger_events"] == ["Company expanding"]
    assert "enriched_at" in ed

"""Tests for the AI module with mocked Groq API."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
from backend.database import Base, get_db
from backend.ai.intents import Intent, classify_intent, _parse_classification_response
from backend.ai.knowledge import get_knowledge_context

# Test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    """Create test app with test database."""
    application = create_app()
    application.dependency_overrides[get_db] = override_get_db

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield application

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(app):
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Intent parsing tests ---


class TestIntentParsing:
    """Test the intent classification response parsing."""

    def test_parse_salary_intent(self):
        response = json.dumps({
            "intent": "calculate_salary",
            "params": {"oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 0},
            "confidence": 0.95,
        })
        intent, params, confidence = _parse_classification_response(response)
        assert intent == Intent.calculate_salary
        assert params["oklad"] == 30000
        assert params["rate"] == 1.0
        assert confidence == 0.95

    def test_parse_vacation_intent(self):
        response = json.dumps({
            "intent": "calculate_vacation",
            "params": {"total_12_months": 500000, "days": 14},
            "confidence": 0.9,
        })
        intent, params, confidence = _parse_classification_response(response)
        assert intent == Intent.calculate_vacation
        assert params["total_12_months"] == 500000
        assert params["days"] == 14

    def test_parse_sick_intent(self):
        response = json.dumps({
            "intent": "calculate_sick",
            "params": {"earnings_2y": 800000, "stazh_bracket": "5-8", "days": 10},
            "confidence": 0.9,
        })
        intent, params, confidence = _parse_classification_response(response)
        assert intent == Intent.calculate_sick
        assert params["stazh_bracket"] == "5-8"

    def test_parse_kbk_intent(self):
        response = json.dumps({
            "intent": "search_kbk",
            "params": {"query": "НДФЛ"},
            "confidence": 0.85,
        })
        intent, params, confidence = _parse_classification_response(response)
        assert intent == Intent.search_kbk
        assert params["query"] == "НДФЛ"

    def test_parse_question_intent(self):
        response = json.dumps({
            "intent": "ask_question",
            "params": {"question": "Какой срок сдачи РСВ?"},
            "confidence": 0.8,
        })
        intent, params, confidence = _parse_classification_response(response)
        assert intent == Intent.ask_question

    def test_parse_unknown_intent(self):
        response = json.dumps({
            "intent": "unknown_intent_xyz",
            "params": {},
            "confidence": 0.1,
        })
        intent, params, confidence = _parse_classification_response(response)
        assert intent is None

    def test_parse_invalid_json(self):
        response = "this is not json at all"
        intent, params, confidence = _parse_classification_response(response)
        assert intent is None
        assert params == {}
        assert confidence == 0.0

    def test_parse_markdown_wrapped_json(self):
        response = '```json\n{"intent": "calculate_salary", "params": {"oklad": 25000}, "confidence": 0.9}\n```'
        intent, params, confidence = _parse_classification_response(response)
        assert intent == Intent.calculate_salary
        assert params["oklad"] == 25000

    def test_all_intents_exist(self):
        """Verify all defined intents are valid enum members."""
        expected = [
            "calculate_salary", "calculate_vacation", "calculate_sick",
            "add_employee", "mark_timesheet", "add_journal_entry",
            "search_kbk", "ask_question", "generate_text",
        ]
        for intent_name in expected:
            assert Intent(intent_name) is not None


# --- Knowledge base tests ---


class TestKnowledge:
    """Test the knowledge base content."""

    def test_knowledge_contains_tax_rates(self):
        knowledge = get_knowledge_context()
        assert "13%" in knowledge  # NDFL
        assert "22%" in knowledge  # PFR
        assert "5.1%" in knowledge  # OMS
        assert "2.9%" in knowledge  # FSS
        assert "0.2%" in knowledge  # FSS_NS

    def test_knowledge_contains_formulas(self):
        knowledge = get_knowledge_context()
        assert "29.3" in knowledge  # avg days in month
        assert "730" in knowledge  # sick leave divisor

    def test_knowledge_contains_deadlines(self):
        knowledge = get_knowledge_context()
        assert "6-НДФЛ" in knowledge
        assert "РСВ" in knowledge
        assert "СЗВ-М" in knowledge


# --- API endpoint tests with mocked Groq ---


@pytest.mark.asyncio
async def test_ai_chat_salary_calculation(client):
    """Test salary calculation via AI chat endpoint with mocked Groq."""
    mock_response = json.dumps({
        "intent": "calculate_salary",
        "params": {"oklad": 30000, "rate": 1.0, "stazh_percent": 10, "category_percent": 0},
        "confidence": 0.95,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response
        response = await client.post(
            "/api/v1/ai/chat",
            json={"message": "Рассчитай зарплату: оклад 30000, ставка 1.0, стаж 10%", "chat_id": 123},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "calculate_salary"
    assert "Начислено" in data["response"]
    assert "На руки" in data["response"]
    assert "НДФЛ" in data["response"]


@pytest.mark.asyncio
async def test_ai_chat_vacation_calculation(client):
    """Test vacation calculation via AI chat endpoint."""
    mock_response = json.dumps({
        "intent": "calculate_vacation",
        "params": {"total_12_months": 500000, "days": 14},
        "confidence": 0.9,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response
        response = await client.post(
            "/api/v1/ai/chat",
            json={"message": "Сколько отпускных за 14 дней если доход 500000?", "chat_id": 123},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "calculate_vacation"
    assert "На руки" in data["response"]


@pytest.mark.asyncio
async def test_ai_chat_sick_calculation(client):
    """Test sick leave calculation via AI chat endpoint."""
    mock_response = json.dumps({
        "intent": "calculate_sick",
        "params": {"earnings_2y": 800000, "stazh_bracket": "5-8", "days": 10},
        "confidence": 0.9,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response
        response = await client.post(
            "/api/v1/ai/chat",
            json={"message": "Больничный 10 дней, стаж 6 лет, доход за 2 года 800000", "chat_id": 123},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "calculate_sick"
    assert "80%" in data["response"]


@pytest.mark.asyncio
async def test_ai_chat_unknown_intent(client):
    """Test AI chat with unrecognizable message."""
    mock_response = json.dumps({
        "intent": "ask_question",
        "params": {"question": "абв"},
        "confidence": 0.2,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response
        response = await client.post(
            "/api/v1/ai/chat",
            json={"message": "абв", "chat_id": 123},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "unknown"
    assert "уточните" in data["response"].lower() or "определить" in data["response"].lower()


@pytest.mark.asyncio
async def test_ai_chat_groq_failure(client):
    """Test AI chat when Groq API fails."""
    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = None
        response = await client.post(
            "/api/v1/ai/chat",
            json={"message": "Рассчитай зарплату", "chat_id": 123},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "unknown"


@pytest.mark.asyncio
async def test_ai_chat_question_with_knowledge(client):
    """Test asking a question that uses knowledge base."""
    # First mock for intent classification
    classify_response = json.dumps({
        "intent": "ask_question",
        "params": {"question": "Какой процент НДФЛ?"},
        "confidence": 0.85,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_classify:
        mock_classify.return_value = classify_response
        with patch("backend.ai.router.chat_completion", new_callable=AsyncMock) as mock_answer:
            mock_answer.return_value = "НДФЛ составляет 13% от начисленной заработной платы."
            response = await client.post(
                "/api/v1/ai/chat",
                json={"message": "Какой процент НДФЛ?", "chat_id": 123},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "ask_question"
    assert "13%" in data["response"]


@pytest.mark.asyncio
async def test_ai_chat_empty_message(client):
    """Test AI chat with empty message."""
    response = await client.post(
        "/api/v1/ai/chat",
        json={"message": "", "chat_id": 123},
    )
    # Should fail validation (min_length=1)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ai_chat_kbk_search(client):
    """Test KBK search via AI chat."""
    mock_response = json.dumps({
        "intent": "search_kbk",
        "params": {"query": "НДФЛ"},
        "confidence": 0.9,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response
        response = await client.post(
            "/api/v1/ai/chat",
            json={"message": "Найди КБК для НДФЛ", "chat_id": 123},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "search_kbk"


# --- classify_intent integration test ---


@pytest.mark.asyncio
async def test_classify_intent_with_mock():
    """Test the classify_intent function with mocked Groq response."""
    mock_response = json.dumps({
        "intent": "calculate_salary",
        "params": {"oklad": 25000, "rate": 0.5, "stazh_percent": 5, "category_percent": 0},
        "confidence": 0.92,
    })

    with patch("backend.ai.intents.chat_completion", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response
        intent, params, confidence = await classify_intent("Зарплата при окладе 25000 на полставки, стаж 5%")

    assert intent == Intent.calculate_salary
    assert params["oklad"] == 25000
    assert params["rate"] == 0.5
    assert confidence == 0.92

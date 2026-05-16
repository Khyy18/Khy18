"""Тесты для LLM Multi-Provider, Rate Limiter и Budget Tracker."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_office.core.database import Base
from ai_office.core.models import TokenUsage
from ai_office.core.rate_limiter import (
    BudgetExhaustedError,
    DailyBudgetTracker,
    Priority,
    RateLimitedError,
    TokenBucketRateLimiter,
)


# --- Rate Limiter Tests ---


@pytest.mark.asyncio
async def test_rate_limiter_acquire_success():
    """Rate limiter пропускает запросы в рамках лимита."""
    limiter = TokenBucketRateLimiter(global_rpm=10, agent_rpm=5)
    result = await limiter.acquire("alice", Priority.NORMAL)
    assert result is True


@pytest.mark.asyncio
async def test_rate_limiter_global_limit():
    """Rate limiter блокирует при исчерпании глобального лимита."""
    limiter = TokenBucketRateLimiter(global_rpm=3, agent_rpm=10)

    # Exhaust global tokens
    for _ in range(3):
        await limiter.acquire("alice", Priority.NORMAL)

    with pytest.raises(RateLimitedError, match="Глобальный лимит"):
        await limiter.acquire("alice", Priority.NORMAL)


@pytest.mark.asyncio
async def test_rate_limiter_agent_limit():
    """Rate limiter блокирует при исчерпании лимита агента."""
    limiter = TokenBucketRateLimiter(global_rpm=100, agent_rpm=2)

    # Exhaust agent tokens
    for _ in range(2):
        await limiter.acquire("alice", Priority.NORMAL)

    with pytest.raises(RateLimitedError, match="Лимит агента"):
        await limiter.acquire("alice", Priority.NORMAL)


@pytest.mark.asyncio
async def test_rate_limiter_urgent_bypasses_agent_limit():
    """URGENT приоритет обходит лимит агента."""
    limiter = TokenBucketRateLimiter(global_rpm=100, agent_rpm=2)

    # Exhaust agent tokens
    for _ in range(2):
        await limiter.acquire("alice", Priority.NORMAL)

    # URGENT bypasses agent limit
    result = await limiter.acquire("alice", Priority.URGENT)
    assert result is True


@pytest.mark.asyncio
async def test_rate_limiter_refill_with_mocked_time():
    """Rate limiter пополняет токены со временем."""
    current_time = [0.0]

    def mock_time():
        return current_time[0]

    limiter = TokenBucketRateLimiter(global_rpm=60, agent_rpm=60, time_func=mock_time)

    # Use 1 token at t=0
    await limiter.acquire("alice", Priority.NORMAL)

    # Exhaust remaining (60 - 1 = 59)
    for _ in range(59):
        await limiter.acquire("alice", Priority.NORMAL)

    # Should be exhausted
    with pytest.raises(RateLimitedError):
        await limiter.acquire("alice", Priority.NORMAL)

    # Advance time by 1 second -> should refill 1 token
    current_time[0] = 1.0
    result = await limiter.acquire("alice", Priority.NORMAL)
    assert result is True


# --- Daily Budget Tracker Tests ---


@pytest.mark.asyncio
async def test_budget_tracker_allows_within_budget():
    """Budget tracker разрешает в рамках бюджета."""
    tracker = DailyBudgetTracker(daily_budget_usd=10.0)
    result = await tracker.check_budget()
    assert result is True


@pytest.mark.asyncio
async def test_budget_tracker_blocks_when_exhausted():
    """Budget tracker блокирует при исчерпании бюджета."""
    tracker = DailyBudgetTracker(daily_budget_usd=1.0)
    await tracker.add_spend(1.0)

    with pytest.raises(BudgetExhaustedError, match="бюджет"):
        await tracker.check_budget()


@pytest.mark.asyncio
async def test_budget_tracker_resets_at_new_day():
    """Budget tracker сбрасывается при наступлении нового дня."""
    current_time = [1700000000.0]  # some timestamp

    def mock_time():
        return current_time[0]

    tracker = DailyBudgetTracker(daily_budget_usd=1.0, time_func=mock_time)
    await tracker.add_spend(1.0)

    # Should be exhausted
    with pytest.raises(BudgetExhaustedError):
        await tracker.check_budget()

    # Advance to next day (add 86400+ seconds)
    current_time[0] += 90000.0
    result = await tracker.check_budget()
    assert result is True


@pytest.mark.asyncio
async def test_budget_tracker_get_today_spend():
    """Budget tracker корректно возвращает расходы за сегодня."""
    tracker = DailyBudgetTracker(daily_budget_usd=10.0)
    await tracker.add_spend(0.5)
    await tracker.add_spend(0.3)
    spend = await tracker.get_today_spend()
    assert abs(spend - 0.8) < 0.0001


# --- LLM Provider Tests ---


@pytest.mark.asyncio
async def test_llm_provider_retry_on_failure():
    """LLM Provider повторяет запрос при ошибке."""
    from ai_office.core.llm_provider import LLMProvider

    provider = LLMProvider()

    mock_response = MagicMock()
    mock_response.content = "Hello"
    mock_response.tool_calls = []
    mock_response.response_metadata = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    call_count = [0]

    async def mock_ainvoke(messages):
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("Transient error")
        return mock_response

    mock_model = MagicMock()
    mock_model.ainvoke = mock_ainvoke

    with patch.object(provider, '_create_chat_model', return_value=mock_model), \
         patch.object(provider, '_log_usage', new_callable=AsyncMock), \
         patch('ai_office.core.llm_provider.settings') as mock_settings, \
         patch('ai_office.core.llm_provider.budget_tracker') as mock_budget, \
         patch('ai_office.core.llm_provider.rate_limiter') as mock_rate:

        mock_settings.llm_max_retries = 3
        mock_settings.enable_rate_limiter = True
        mock_budget.check_budget = AsyncMock()
        mock_rate.acquire = AsyncMock(return_value=True)

        # Patch asyncio.sleep to not actually sleep
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await provider.ainvoke_with_retry(
                messages=[],
                agent_name="test",
            )

    assert result == mock_response
    assert call_count[0] == 3


@pytest.mark.asyncio
async def test_llm_provider_fallback_to_next_provider():
    """LLM Provider переключается на следующего провайдера при ошибке."""
    from ai_office.core.llm_provider import LLMProvider

    provider = LLMProvider()
    provider._providers = ["openai", "anthropic"]

    mock_response = MagicMock()
    mock_response.content = "From anthropic"
    mock_response.tool_calls = []
    mock_response.response_metadata = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    call_count = {"openai": 0, "anthropic": 0}

    def mock_create(prov, **kwargs):
        model = MagicMock()

        async def _invoke(messages):
            call_count[prov] += 1
            if prov == "openai":
                raise Exception("OpenAI down")
            return mock_response

        model.ainvoke = _invoke
        return model

    with patch.object(provider, '_create_chat_model', side_effect=mock_create), \
         patch.object(provider, '_log_usage', new_callable=AsyncMock), \
         patch('ai_office.core.llm_provider.settings') as mock_settings, \
         patch('ai_office.core.llm_provider.budget_tracker') as mock_budget, \
         patch('ai_office.core.llm_provider.rate_limiter') as mock_rate:

        mock_settings.llm_max_retries = 2
        mock_settings.enable_rate_limiter = True
        mock_budget.check_budget = AsyncMock()
        mock_rate.acquire = AsyncMock(return_value=True)

        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await provider.ainvoke_with_retry(
                messages=[],
                agent_name="test",
            )

    assert result == mock_response
    assert call_count["openai"] == 2  # max retries
    assert call_count["anthropic"] == 1  # success on first try


@pytest.mark.asyncio
async def test_llm_provider_logs_token_usage_to_db():
    """LLM Provider записывает использование токенов в БД."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from ai_office.core.llm_provider import LLMProvider

    provider = LLMProvider()

    mock_response = MagicMock()
    mock_response.content = "Test response"
    mock_response.tool_calls = []
    mock_response.response_metadata = {
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50}
    }

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(return_value=mock_response)

    with patch.object(provider, '_create_chat_model', return_value=mock_model), \
         patch('ai_office.core.database.async_session', session_factory), \
         patch('ai_office.core.llm_provider.settings') as mock_settings, \
         patch('ai_office.core.llm_provider.budget_tracker') as mock_budget, \
         patch('ai_office.core.llm_provider.rate_limiter') as mock_rate:

        mock_settings.llm_max_retries = 3
        mock_settings.enable_rate_limiter = True
        mock_settings.openai_model = "gpt-4o-mini"
        mock_budget.check_budget = AsyncMock()
        mock_budget.add_spend = AsyncMock()
        mock_rate.acquire = AsyncMock(return_value=True)

        provider._providers = ["openai"]

        result = await provider.ainvoke_with_retry(
            messages=[],
            agent_name="alice",
        )

    # Check DB
    async with session_factory() as session:
        query = select(TokenUsage)
        res = await session.execute(query)
        usage = res.scalar_one()

    assert usage.provider == "openai"
    assert usage.model == "gpt-4o-mini"
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50
    assert usage.agent_name == "alice"
    assert usage.estimated_cost_usd > 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_llm_provider_budget_exhausted_raises():
    """LLM Provider raises BudgetExhaustedError when budget is exhausted."""
    from ai_office.core.llm_provider import LLMProvider

    provider = LLMProvider()

    with patch('ai_office.core.llm_provider.settings') as mock_settings, \
         patch('ai_office.core.llm_provider.budget_tracker') as mock_budget, \
         patch('ai_office.core.llm_provider.rate_limiter') as mock_rate:

        mock_settings.enable_rate_limiter = True
        mock_budget.check_budget = AsyncMock(
            side_effect=BudgetExhaustedError("Budget exhausted")
        )
        mock_rate.acquire = AsyncMock(return_value=True)

        with pytest.raises(BudgetExhaustedError):
            await provider.ainvoke_with_retry(
                messages=[],
                agent_name="test",
            )

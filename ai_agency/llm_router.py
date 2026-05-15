"""Multi-provider LLM router: OpenAI -> Groq -> Anthropic -> Together.ai with auto-switching."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import config

# Graceful imports
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from openai import AsyncOpenAI as _TogetherClient
except ImportError:
    _TogetherClient = None

try:
    from resilience import CircuitBreaker
except ImportError:
    CircuitBreaker = None

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetrics:
    """Metrics for an LLM provider."""

    total_calls: int = 0
    total_errors: int = 0
    total_latency: float = 0.0
    cost_per_token: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_errors / self.total_calls

    @property
    def avg_latency(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency / self.total_calls


@dataclass
class LLMProvider:
    """Represents an LLM provider with health check and call capabilities."""

    name: str
    priority: int
    cost_per_token: float
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)
    _circuit: object = field(default=None, repr=False)
    _client: object = field(default=None, repr=False)
    _healthy: bool = field(default=True, repr=False)

    def __post_init__(self):
        self.metrics.cost_per_token = self.cost_per_token
        if CircuitBreaker is not None:
            self._circuit = CircuitBreaker(
                failure_threshold=3, cooldown_seconds=120, name=self.name
            )

    def is_available(self) -> bool:
        """Check if provider can accept requests."""
        if not self._healthy:
            return False
        if self._circuit and not self._circuit.can_execute():
            return False
        return True

    def record_success(self, latency: float) -> None:
        """Record a successful call."""
        self.metrics.total_calls += 1
        self.metrics.total_latency += latency
        if self._circuit:
            self._circuit.record_success()

    def record_failure(self) -> None:
        """Record a failed call."""
        self.metrics.total_calls += 1
        self.metrics.total_errors += 1
        if self._circuit:
            self._circuit.record_failure()


# Lazy singleton providers
_providers: Optional[List[LLMProvider]] = None
_health_check_task: Optional[asyncio.Task] = None


def _init_providers() -> List[LLMProvider]:
    """Initialize all configured providers."""
    providers = []

    # OpenAI (priority 0 - highest)
    if config.OPENAI_API_KEY and AsyncOpenAI is not None:
        p = LLMProvider(name="openai", priority=0, cost_per_token=0.00003)
        p._client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        providers.append(p)

    # Groq (priority 1)
    if config.GROQ_API_KEY and AsyncGroq is not None:
        p = LLMProvider(name="groq", priority=1, cost_per_token=0.000005)
        p._client = AsyncGroq(api_key=config.GROQ_API_KEY)
        providers.append(p)

    # Anthropic (priority 2)
    if config.ANTHROPIC_API_KEY and anthropic is not None:
        p = LLMProvider(name="anthropic", priority=2, cost_per_token=0.000025)
        p._client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
        providers.append(p)

    # Together.ai (priority 3) - uses OpenAI-compatible API
    if config.TOGETHER_API_KEY and _TogetherClient is not None:
        p = LLMProvider(name="together", priority=3, cost_per_token=0.000002)
        p._client = _TogetherClient(
            api_key=config.TOGETHER_API_KEY,
            base_url="https://api.together.xyz/v1",
        )
        providers.append(p)

    return providers


def _get_providers() -> List[LLMProvider]:
    """Get or initialize singleton providers list."""
    global _providers
    if _providers is None:
        _providers = _init_providers()
    return _providers


async def _call_provider(provider: LLMProvider, messages: List[Dict[str, str]],
                         temperature: float, max_tokens: int) -> Optional[str]:
    """Call a specific provider and return the response text."""
    start = time.time()
    try:
        if provider.name == "openai":
            response = await provider._client.chat.completions.create(
                model=config.DEFAULT_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content.strip()

        elif provider.name == "groq":
            response = await provider._client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content.strip()

        elif provider.name == "anthropic":
            # Convert messages format for Anthropic
            system_msg = ""
            user_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    user_messages.append(msg)
            kwargs = {
                "model": "claude-3-haiku-20240307",
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_msg:
                kwargs["system"] = system_msg
            response = await provider._client.messages.create(**kwargs)
            result = response.content[0].text.strip()

        elif provider.name == "together":
            response = await provider._client.chat.completions.create(
                model="meta-llama/Llama-3-70b-chat-hf",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content.strip()

        else:
            return None

        latency = time.time() - start
        provider.record_success(latency)
        logger.debug("LLM Router: %s responded in %.2fs", provider.name, latency)
        return result

    except Exception as e:
        provider.record_failure()
        logger.warning("LLM Router: %s failed: %s", provider.name, str(e))
        return None


def _select_provider(providers: List[LLMProvider]) -> Optional[LLMProvider]:
    """Select the cheapest available (working) provider."""
    available = [p for p in providers if p.is_available()]
    if not available:
        return None
    # Sort by cost_per_token (cheapest first), then by priority
    available.sort(key=lambda p: (p.cost_per_token, p.priority))
    return available[0]


async def generate(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> Optional[str]:
    """
    Generate text using the best available LLM provider.

    Tries providers in priority order, auto-switches on error.
    Returns None if all providers fail.
    """
    providers = _get_providers()
    if not providers:
        logger.error("LLM Router: no providers configured")
        return None

    # First, try the cheapest available provider
    best = _select_provider(providers)
    if best:
        result = await _call_provider(best, messages, temperature, max_tokens)
        if result:
            return result

    # If cheapest failed, try all providers in priority order
    sorted_providers = sorted(providers, key=lambda p: p.priority)
    for provider in sorted_providers:
        if provider == best:
            continue  # already tried
        if not provider.is_available():
            continue
        result = await _call_provider(provider, messages, temperature, max_tokens)
        if result:
            return result

    # Last resort: try all providers ignoring circuit breaker
    for provider in sorted_providers:
        if provider._client is None:
            continue
        result = await _call_provider(provider, messages, temperature, max_tokens)
        if result:
            return result

    logger.error("LLM Router: all providers failed")
    return None


async def health_check_provider(provider: LLMProvider) -> bool:
    """Run a lightweight health check on a provider."""
    test_messages = [{"role": "user", "content": "ping"}]
    try:
        result = await _call_provider(provider, test_messages, 0.0, 5)
        provider._healthy = result is not None
        return provider._healthy
    except Exception:
        provider._healthy = False
        return False


async def _health_check_loop() -> None:
    """Background task: health-check all providers every 5 minutes."""
    while True:
        try:
            providers = _get_providers()
            for provider in providers:
                await health_check_provider(provider)
                await asyncio.sleep(2)  # small delay between checks
        except Exception as e:
            logger.error("LLM Router health check error: %s", e)
        await asyncio.sleep(300)  # 5 minutes


def start_health_checks() -> None:
    """Start the background health check loop."""
    global _health_check_task
    if _health_check_task is None or _health_check_task.done():
        loop = asyncio.get_event_loop()
        _health_check_task = loop.create_task(_health_check_loop())
        logger.info("LLM Router: health check loop started")


def get_provider_stats() -> List[Dict]:
    """Get stats for all providers (for monitoring/admin)."""
    providers = _get_providers()
    stats = []
    for p in providers:
        stats.append({
            "name": p.name,
            "priority": p.priority,
            "healthy": p._healthy,
            "available": p.is_available(),
            "cost_per_token": p.cost_per_token,
            "total_calls": p.metrics.total_calls,
            "error_rate": p.metrics.error_rate,
            "avg_latency": p.metrics.avg_latency,
        })
    return stats

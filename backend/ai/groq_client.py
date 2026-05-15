"""Groq SDK async wrapper for LLM chat completions."""

import asyncio
import logging
from typing import List, Dict, Optional

from groq import Groq, APIError, RateLimitError

from backend.config import settings

logger = logging.getLogger(__name__)

# Default model
DEFAULT_MODEL = "llama-3.1-70b-versatile"
MAX_RETRIES = 3
RETRY_DELAY = 1.0


def _get_client() -> Groq:
    """Create a Groq client instance."""
    return Groq(api_key=settings.GROQ_API_KEY)


async def chat_completion(
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1024,
) -> Optional[str]:
    """Send chat completion request to Groq API with retry logic.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: Model name to use.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens in response.

    Returns:
        Response content string or None on failure.
    """
    client = _get_client()

    for attempt in range(MAX_RETRIES):
        try:
            # Groq SDK is synchronous, run in thread pool
            response = await asyncio.to_thread(
                client.chat.completions.create,
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response.choices:
                return response.choices[0].message.content
            return None

        except RateLimitError as e:
            logger.warning(f"Rate limit hit (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error("Max retries exceeded for rate limit")
                return None

        except APIError as e:
            logger.error(f"Groq API error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                return None

        except Exception as e:
            logger.error(f"Unexpected error calling Groq: {e}")
            return None

    return None

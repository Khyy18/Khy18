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

# Module-level singleton client for connection reuse
_client: Optional[Groq] = None


def _get_client() -> Groq:
    """Get or create the singleton Groq client instance."""
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


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


async def vision_completion(
    image_base64: str,
    prompt: str,
    model: str = "llama-3.2-90b-vision-preview",
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> Optional[str]:
    """Send vision completion request to Groq API with retry logic.

    Args:
        image_base64: Base64-encoded image data.
        prompt: Text prompt to accompany the image.
        model: Vision model name to use.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.

    Returns:
        Response content string or None on failure.
    """
    client = _get_client()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                },
            ],
        }
    ]

    for attempt in range(MAX_RETRIES):
        try:
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
            logger.error(f"Unexpected error calling Groq vision: {e}")
            return None

    return None

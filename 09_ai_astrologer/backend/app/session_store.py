"""Redis-backed session store for AI Astrologer."""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.models import UserSession, CallStatus

logger = logging.getLogger(__name__)

SESSION_TTL = 7200  # 2 hours in seconds


class RedisSessionStore:
    """Store and retrieve session state from Redis."""

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis = redis_client

    async def save_session(self, session: UserSession) -> None:
        """Save a UserSession to Redis with TTL."""
        if not self.redis:
            logger.warning("Redis not available, session not persisted")
            return
        key = f"session:{session.session_id}"
        data = {
            "user_id": session.user_id,
            "session_id": session.session_id,
            "balance": session.balance,
            "status": session.status.value,
            "natal_chart": session.natal_chart.model_dump() if session.natal_chart else None,
        }
        await self.redis.set(key, json.dumps(data), ex=SESSION_TTL)

    async def get_session(self, session_id: str) -> Optional[UserSession]:
        """Retrieve a UserSession from Redis."""
        if not self.redis:
            return None
        key = f"session:{session_id}"
        raw = await self.redis.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        from app.models import NatalChart

        natal_chart = None
        if data.get("natal_chart"):
            natal_chart = NatalChart(**data["natal_chart"])
        return UserSession(
            user_id=data["user_id"],
            session_id=data["session_id"],
            balance=data["balance"],
            status=CallStatus(data["status"]),
            natal_chart=natal_chart,
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session from Redis."""
        if not self.redis:
            return
        key = f"session:{session_id}"
        await self.redis.delete(key)

    async def save_history(
        self, session_id: str, history: list[dict[str, str]]
    ) -> None:
        """Save conversation history to Redis."""
        if not self.redis:
            return
        key = f"history:{session_id}"
        await self.redis.set(key, json.dumps(history), ex=SESSION_TTL)

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Retrieve conversation history from Redis."""
        if not self.redis:
            return []
        key = f"history:{session_id}"
        raw = await self.redis.get(key)
        if not raw:
            return []
        return json.loads(raw)

    async def save_pipeline_context(
        self, session_id: str, system_prompt: str
    ) -> None:
        """Save pipeline context (system prompt) to Redis."""
        if not self.redis:
            return
        key = f"pipeline:{session_id}"
        data = {"system_prompt": system_prompt}
        await self.redis.set(key, json.dumps(data), ex=SESSION_TTL)

    async def get_pipeline_context(self, session_id: str) -> Optional[str]:
        """Retrieve pipeline context (system prompt) from Redis."""
        if not self.redis:
            return None
        key = f"pipeline:{session_id}"
        raw = await self.redis.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("system_prompt")

    async def save_token(self, session_id: str, token: str) -> None:
        """Save authentication token for a session."""
        if not self.redis:
            return
        key = f"token:{session_id}"
        await self.redis.set(key, token, ex=SESSION_TTL)

    async def get_token(self, session_id: str) -> Optional[str]:
        """Retrieve authentication token for a session."""
        if not self.redis:
            return None
        key = f"token:{session_id}"
        return await self.redis.get(key)

    async def delete_token(self, session_id: str) -> None:
        """Delete authentication token for a session."""
        if not self.redis:
            return
        key = f"token:{session_id}"
        await self.redis.delete(key)

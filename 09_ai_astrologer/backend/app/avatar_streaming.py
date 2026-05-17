"""Simli API integration for lip-sync avatar video streaming."""

import logging
from typing import Optional

import httpx

from app.config import settings
from app.http_client import get_http_client

logger = logging.getLogger(__name__)


class SimliAvatarStreamer:
    """Streams audio to Simli API and receives lip-synced video chunks."""

    SIMLI_API_BASE = "https://api.simli.ai"

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._client = http_client
        self._session_id: Optional[str] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client:
            return self._client
        return get_http_client()

    @property
    def has_session(self) -> bool:
        """Whether an active Simli session exists."""
        return self._session_id is not None

    @property
    def is_configured(self) -> bool:
        return bool(settings.simli_api_key)

    async def create_session(self) -> Optional[str]:
        """Create a Simli audio-to-video session."""
        if not self.is_configured:
            return None
        try:
            response = await self.client.post(
                f"{self.SIMLI_API_BASE}/startAudioToVideoSession",
                headers={
                    "Authorization": f"Bearer {settings.simli_api_key}",
                    "Content-Type": "application/json",
                },
                json={"faceId": "default", "isJPG": False},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            self._session_id = data.get("session_id")
            return self._session_id
        except Exception as e:
            logger.error(f"Failed to create Simli session: {e}")
            return None

    async def send_audio_get_video(self, audio_bytes: bytes) -> Optional[bytes]:
        """Send audio to Simli and receive video bytes."""
        if not self.is_configured or not self._session_id:
            return None
        try:
            response = await self.client.post(
                f"{self.SIMLI_API_BASE}/audioToVideo",
                headers={
                    "Authorization": f"Bearer {settings.simli_api_key}",
                    "Content-Type": "application/octet-stream",
                    "X-Session-Id": self._session_id,
                },
                content=audio_bytes,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.warning(f"Simli audio-to-video failed: {e}")
            return None

    async def close_session(self) -> None:
        """Close the Simli session."""
        if not self.is_configured or not self._session_id:
            return
        try:
            await self.client.post(
                f"{self.SIMLI_API_BASE}/closeSession",
                headers={"Authorization": f"Bearer {settings.simli_api_key}"},
                json={"session_id": self._session_id},
                timeout=5.0,
            )
        except Exception:
            pass
        self._session_id = None

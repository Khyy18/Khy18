"""
Endpoint для получения LiveKit токена доступа.
В production здесь используется livekit-api для генерации реального AccessToken.
Сейчас возвращает mock-ответ для разработки (development stub).
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/call", tags=["call"])


class LiveKitTokenRequest(BaseModel):
    session_id: str


class LiveKitTokenResponse(BaseModel):
    token: str
    url: str


@router.post("/livekit-token", response_model=LiveKitTokenResponse)
async def get_livekit_token(
    request: LiveKitTokenRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Получение LiveKit access token для подключения к видео-комнате.

    В production:
        from livekit.api import AccessToken, VideoGrant
        token = AccessToken(api_key, api_secret)
        token.identity = user_id
        token.add_grant(VideoGrant(room_join=True, room=request.session_id))
        return {"token": token.to_jwt(), "url": settings.LIVEKIT_URL}

    Пока возвращаем mock для разработки.
    """
    # Development stub - replace with real LiveKit token generation in production
    logger.warning(
        "LiveKit token endpoint is serving mock data. Set LIVEKIT_API_KEY for production."
    )
    return LiveKitTokenResponse(
        token="mock-livekit-token",
        url="wss://livekit.example.com",
    )

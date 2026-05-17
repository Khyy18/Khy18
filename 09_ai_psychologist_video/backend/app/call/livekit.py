"""
Endpoint для получения LiveKit токена доступа.
В production здесь используется livekit-api для генерации реального AccessToken.
Сейчас возвращает mock-ответ для разработки.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user_id

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
    return LiveKitTokenResponse(
        token="mock-livekit-token",
        url="wss://livekit.example.com",
    )

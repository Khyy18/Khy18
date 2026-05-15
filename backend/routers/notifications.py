"""Push notification endpoints."""
import logging
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.auth import verify_bearer_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# In-memory token storage
_registered_tokens: Dict[str, dict] = {}


class TokenRegisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=1)
    chat_id: int = Field(default=0)
    device_info: Optional[str] = None


class NotificationSendRequest(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    target_chat_ids: Optional[List[int]] = None


class TokenRegisterResponse(BaseModel):
    status: str
    token_count: int


class NotificationSendResponse(BaseModel):
    status: str
    sent_to: int


@router.post("/register", response_model=TokenRegisterResponse)
async def register_token(data: TokenRegisterRequest):
    """Register an FCM token for push notifications."""
    _registered_tokens[data.fcm_token] = {
        "chat_id": data.chat_id,
        "device_info": data.device_info,
        "registered_at": datetime.now().isoformat(),
    }
    return TokenRegisterResponse(
        status="registered",
        token_count=len(_registered_tokens),
    )


@router.post("/send", response_model=NotificationSendResponse)
async def send_notification(
    data: NotificationSendRequest,
    _token: str = Depends(verify_bearer_token),
):
    """Send push notification (stub - logs the request)."""
    targets = _registered_tokens
    if data.target_chat_ids:
        targets = {
            k: v for k, v in _registered_tokens.items()
            if v.get("chat_id") in data.target_chat_ids
        }

    logger.info(
        f"Push notification stub: title='{data.title}', body='{data.body}', "
        f"targets={len(targets)} devices"
    )

    return NotificationSendResponse(
        status="sent",
        sent_to=len(targets),
    )


@router.get("/tokens")
async def get_tokens_count(
    _token: str = Depends(verify_bearer_token),
):
    """Get count of registered FCM tokens."""
    return {"token_count": len(_registered_tokens)}

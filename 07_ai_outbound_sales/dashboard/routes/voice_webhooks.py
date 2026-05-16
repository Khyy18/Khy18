"""Voice Webhook routes - Twilio status callbacks, media streams, and AMD."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice/twilio", tags=["voice-webhooks"])


def _validate_twilio_signature(
    url: str,
    params: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    """Validate a Twilio request signature.

    Args:
        url: The full URL of the request.
        params: The POST parameters.
        signature: The X-Twilio-Signature header value.
        auth_token: The Twilio auth token.

    Returns:
        True if the signature is valid.
    """
    if not auth_token or not signature:
        return False

    # Sort the POST parameters and append to URL
    sorted_params = sorted(params.items())
    data = url + "".join(f"{k}{v}" for k, v in sorted_params)

    # Compute HMAC-SHA1
    import base64

    computed = hmac.HMAC(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    expected = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(expected, signature)


async def _get_call_manager(request: Request) -> Any:
    """Get the call_manager from app state."""
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service not initialized",
        )
    return call_manager


@router.post("/status")
async def twilio_status_callback(request: Request) -> JSONResponse:
    """Handle Twilio call status callbacks.

    Receives Form data with CallSid, CallStatus, and optionally CallDuration.
    Updates the call record via call_manager.
    """
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        return JSONResponse(
            content={"error": "Voice service not initialized"},
            status_code=503,
        )

    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    call_duration = form_data.get("CallDuration")

    if not call_sid:
        return JSONResponse(
            content={"error": "Missing CallSid"},
            status_code=400,
        )

    # Validate Twilio signature if auth token is configured
    from core.config import settings

    if settings.twilio_auth_token:
        signature = request.headers.get("X-Twilio-Signature", "")
        if not signature:
            logger.warning("Missing X-Twilio-Signature header for status callback")
            return JSONResponse(
                content={"error": "Missing signature"},
                status_code=403,
            )
        url = str(request.url)
        params = dict(form_data)
        if not _validate_twilio_signature(
            url, params, signature, settings.twilio_auth_token
        ):
            logger.warning("Invalid Twilio signature for status callback")
            return JSONResponse(
                content={"error": "Invalid signature"},
                status_code=403,
            )

    duration = int(call_duration) if call_duration else None

    try:
        await call_manager.handle_status_update(
            call_sid=str(call_sid),
            status=str(call_status),
            duration=duration,
        )
    except Exception as exc:
        logger.error("Error handling status update for %s: %s", call_sid, exc)
        return JSONResponse(
            content={"error": "Internal error"},
            status_code=500,
        )

    return JSONResponse(content={"status": "ok"})


@router.websocket("/stream")
async def twilio_media_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint for Twilio Media Streams.

    Receives base64-encoded audio from Twilio and forwards to the call manager
    for STT processing and TTS response streaming.
    """
    await websocket.accept()

    call_manager = getattr(websocket.app.state, "call_manager", None)
    if call_manager is None:
        await websocket.close(code=1011, reason="Voice service not initialized")
        return

    import json

    # Wait for the initial 'start' event to get the call SID and stream SID
    call_sid = ""
    stream_sid = ""
    try:
        initial_msg = await websocket.receive_text()
        data = json.loads(initial_msg)
        if data.get("event") == "connected":
            # Wait for the start event
            start_msg = await websocket.receive_text()
            start_data = json.loads(start_msg)
            if start_data.get("event") == "start":
                call_sid = start_data.get("start", {}).get("callSid", "")
                stream_sid = start_data.get("start", {}).get("streamSid", "")
        elif data.get("event") == "start":
            call_sid = data.get("start", {}).get("callSid", "")
            stream_sid = data.get("start", {}).get("streamSid", "")
    except Exception as exc:
        logger.error("Error receiving initial WebSocket message: %s", exc)
        await websocket.close(code=1011)
        return

    if not call_sid:
        logger.warning("No call SID received in media stream start")
        await websocket.close(code=1008, reason="No call SID")
        return

    try:
        await call_manager.handle_media_stream(websocket, call_sid, stream_sid=stream_sid)
    except Exception as exc:
        logger.error("Media stream error for call %s: %s", call_sid, exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post("/amd")
async def twilio_amd_callback(request: Request) -> JSONResponse:
    """Handle Twilio Answering Machine Detection (AMD) callback.

    Receives Form data with CallSid and AnsweredBy fields.
    Routes to call_manager for appropriate handling.
    """
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        return JSONResponse(
            content={"error": "Voice service not initialized"},
            status_code=503,
        )

    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    answered_by = form_data.get("AnsweredBy", "")

    if not call_sid:
        return JSONResponse(
            content={"error": "Missing CallSid"},
            status_code=400,
        )

    # Validate Twilio signature if auth token is configured
    from core.config import settings

    if settings.twilio_auth_token:
        signature = request.headers.get("X-Twilio-Signature", "")
        if not signature:
            logger.warning("Missing X-Twilio-Signature header for AMD callback")
            return JSONResponse(
                content={"error": "Missing signature"},
                status_code=403,
            )
        url = str(request.url)
        params = dict(form_data)
        if not _validate_twilio_signature(
            url, params, signature, settings.twilio_auth_token
        ):
            logger.warning("Invalid Twilio signature for AMD callback")
            return JSONResponse(
                content={"error": "Invalid signature"},
                status_code=403,
            )

    try:
        await call_manager.handle_amd_result(
            call_sid=str(call_sid),
            answered_by=str(answered_by),
        )
    except Exception as exc:
        logger.error("Error handling AMD result for %s: %s", call_sid, exc)
        return JSONResponse(
            content={"error": "Internal error"},
            status_code=500,
        )

    return JSONResponse(content={"status": "ok"})

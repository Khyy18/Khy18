"""FastAPI application with REST and WebSocket endpoints for AI Astrologer."""

import asyncio
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.astro import calculate_natal_chart
from app.billing import billing_manager
from app.config import settings
from app.models import (
    BalanceTopupRequest,
    BalanceTopupResponse,
    BirthData,
    CallStatus,
    SessionStartRequest,
    SessionStartResponse,
    UserSession,
)
from app.ai_pipeline import AIPipeline
from app.prompts import build_session_prompt

logger = logging.getLogger(__name__)

sessions: dict[str, UserSession] = {}
pipelines: dict[str, AIPipeline] = {}
session_tokens: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect/disconnect Redis."""
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        billing_manager.redis = redis_client
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis not available: {e}. Billing will be limited.")
        billing_manager.redis = None

    yield

    if billing_manager.redis:
        await billing_manager.redis.close()
        logger.info("Redis disconnected")


app = FastAPI(
    title="AI Astrologer",
    description="Autonomous AI astrologer with natal chart calculation and voice interaction",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/session/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """Start a new astrology session: calculate natal chart, create session."""
    natal_chart = calculate_natal_chart(request.birth_data)

    session_id = str(uuid.uuid4())

    session = UserSession(
        user_id=request.user_id,
        session_id=session_id,
        balance=request.balance,
        status=CallStatus.CONNECTING,
        natal_chart=natal_chart,
    )
    sessions[session_id] = session

    if billing_manager.redis:
        await billing_manager.set_balance(request.user_id, request.balance)

    session_prompt = build_session_prompt(natal_chart)
    pipelines[session_id] = AIPipeline(system_prompt=session_prompt)

    # Generate a session-specific token for WebSocket authentication
    token = secrets.token_urlsafe(32)
    session_tokens[session_id] = token

    return SessionStartResponse(
        session_id=session_id,
        natal_chart=natal_chart,
        balance=request.balance,
        token=token,
    )


@app.get("/api/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get current session status."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session.status.value,
        "balance": session.balance,
        "user_id": session.user_id,
    }


@app.post("/api/balance/topup", response_model=BalanceTopupResponse)
async def topup_balance(request: BalanceTopupRequest):
    """Add coins to user balance."""
    if billing_manager.redis:
        new_balance = await billing_manager.topup_balance(
            request.user_id, request.amount
        )
    else:
        new_balance = request.amount

    for session in sessions.values():
        if session.user_id == request.user_id:
            session.balance = new_balance

    return BalanceTopupResponse(user_id=request.user_id, new_balance=new_balance)


@app.websocket("/ws/call/{session_id}")
async def websocket_call(websocket: WebSocket, session_id: str, token: str = Query(default="")):
    """WebSocket endpoint for real-time audio/video communication."""
    session = sessions.get(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    # Verify token
    expected_token = session_tokens.get(session_id)
    if not expected_token or token != expected_token:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    session.status = CallStatus.ACTIVE

    pipeline = pipelines.get(session_id)
    if not pipeline:
        await websocket.close(code=4005, reason="Pipeline not initialized")
        return

    try:
        while True:
            data = await websocket.receive_bytes()

            result = await pipeline.process_audio(data)

            await websocket.send_json({
                "type": "response",
                "transcript": result["transcript"],
                "response_text": result["response_text"],
                "has_audio": len(result["audio_bytes"]) > 0,
                "has_video": result["video_bytes"] is not None,
            })

            if result["audio_bytes"]:
                await websocket.send_bytes(result["audio_bytes"])

    except WebSocketDisconnect:
        logger.info(f"Call WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"Call WebSocket error for session {session_id}: {e}")
    finally:
        session.status = CallStatus.ENDED
        await billing_manager.stop_billing_loop(session_id)
        # Cleanup session and pipeline to prevent memory leak
        sessions.pop(session_id, None)
        pipelines.pop(session_id, None)
        session_tokens.pop(session_id, None)


@app.websocket("/ws/billing/{session_id}")
async def websocket_billing(websocket: WebSocket, session_id: str, token: str = Query(default="")):
    """WebSocket endpoint for billing updates."""
    session = sessions.get(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    # Verify token
    expected_token = session_tokens.get(session_id)
    if not expected_token or token != expected_token:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    await billing_manager.start_billing_loop(
        session_id, session.user_id, websocket
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"Billing WebSocket disconnected for session {session_id}")
    finally:
        await billing_manager.stop_billing_loop(session_id)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "ai-astrologer"}

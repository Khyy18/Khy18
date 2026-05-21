"""FastAPI application with REST and WebSocket endpoints for AI Astrologer."""

import asyncio
import json
import logging
import secrets
import signal
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.astro import calculate_natal_chart
from app.billing import billing_manager
from app.config import settings
from app.http_client import create_http_client, set_http_client, close_http_client, get_http_client
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
from app.session_store import RedisSessionStore
from app.telegram_auth import get_telegram_user
from app.metrics import create_instrumentator, active_calls
from app.rate_limiter import rate_limiter, rate_limit
from app.geocoding import router as geocoding_router
from app.payments import router as payments_router

logger = logging.getLogger(__name__)

# Graceful shutdown state
_shutting_down = False
_shutdown_event: Optional[asyncio.Event] = None


def is_shutting_down() -> bool:
    """Check if the application is in shutdown mode."""
    return _shutting_down


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect/disconnect Redis, create shared HTTP client."""
    global _shutting_down, _shutdown_event
    _shutting_down = False
    _shutdown_event = asyncio.Event()

    # Create shared httpx client
    http_client = create_http_client()
    set_http_client(http_client)
    app.state.http_client = http_client

    # Connect to Redis
    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        billing_manager.redis = redis_client
        rate_limiter.redis = redis_client
        app.state.session_store = RedisSessionStore(redis_client)
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis not available: {e}. Sessions/billing will be limited.")
        billing_manager.redis = None
        rate_limiter.redis = None
        app.state.session_store = RedisSessionStore(None)

    # Initialize database if configured
    try:
        from app.database import init_database
        await init_database()
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")

    # Start billing scheduler
    await billing_manager.start_scheduler()

    # Set up Prometheus metrics
    instrumentator = create_instrumentator()
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics")

    # Set up graceful shutdown signal handlers
    loop = asyncio.get_event_loop()

    def _shutdown_handler():
        global _shutting_down
        _shutting_down = True
        logger.info("Shutdown signal received, stopping new sessions")
        if _shutdown_event:
            _shutdown_event.set()

    try:
        loop.add_signal_handler(signal.SIGTERM, _shutdown_handler)
        loop.add_signal_handler(signal.SIGINT, _shutdown_handler)
    except (NotImplementedError, RuntimeError):
        # Signal handlers not supported on this platform (e.g., Windows)
        pass

    yield

    # Graceful shutdown: wait for active billing sessions
    if billing_manager.get_active_session_count() > 0:
        logger.info(
            f"Waiting for {billing_manager.get_active_session_count()} active sessions..."
        )
        # Wait up to 30 seconds for sessions to complete
        for _ in range(30):
            if billing_manager.get_active_session_count() == 0:
                break
            await asyncio.sleep(1)
        else:
            logger.warning("Shutdown timeout: force-stopping remaining sessions")

    # Stop scheduler
    await billing_manager.stop_scheduler()

    # Close database
    try:
        from app.database import close_database
        await close_database()
    except Exception:
        pass

    # Cleanup
    await close_http_client()
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

# Register routers
app.include_router(geocoding_router)
app.include_router(payments_router)


@app.post("/api/session/start", response_model=SessionStartResponse)
async def start_session(
    request: SessionStartRequest,
    telegram_user: str = Depends(get_telegram_user),
    _rate_check=Depends(rate_limit("session_start", 10, 60)),
):
    """Start a new astrology session: calculate natal chart, create session."""
    # Reject new sessions during graceful shutdown
    if _shutting_down:
        raise HTTPException(
            status_code=503,
            detail="Server is shutting down. Please try again later.",
        )

    natal_chart = calculate_natal_chart(request.birth_data)

    session_id = str(uuid.uuid4())

    session = UserSession(
        user_id=request.user_id,
        session_id=session_id,
        balance=request.balance,
        status=CallStatus.CONNECTING,
        natal_chart=natal_chart,
    )

    # Save session to Redis
    store: RedisSessionStore = app.state.session_store
    await store.save_session(session)

    if billing_manager.redis:
        await billing_manager.set_balance(request.user_id, request.balance)

    session_prompt = build_session_prompt(natal_chart)
    await store.save_pipeline_context(session_id, session_prompt)

    # Generate a session-specific token and store in Redis
    token = secrets.token_urlsafe(32)
    await store.save_token(session_id, token)

    return SessionStartResponse(
        session_id=session_id,
        natal_chart=natal_chart,
        balance=request.balance,
        token=token,
    )


@app.get("/api/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get current session status."""
    store: RedisSessionStore = app.state.session_store
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session.status.value,
        "balance": session.balance,
        "user_id": session.user_id,
    }


@app.post("/api/balance/topup", response_model=BalanceTopupResponse)
async def topup_balance(
    request: BalanceTopupRequest,
    telegram_user: str = Depends(get_telegram_user),
    _rate_check=Depends(rate_limit("topup", 5, 60)),
):
    """Add coins to user balance."""
    if billing_manager.redis:
        new_balance = await billing_manager.topup_balance(
            request.user_id, request.amount
        )
    else:
        new_balance = request.amount

    return BalanceTopupResponse(user_id=request.user_id, new_balance=new_balance)


async def _authenticate_websocket(websocket: WebSocket, session_id: str) -> bool:
    """Authenticate WebSocket via first-message auth protocol.

    Expects the first message to be JSON: {"type": "auth", "token": "..."}
    Validates token against Redis. Returns True if auth succeeds.
    """
    try:
        # Wait for auth message with a timeout
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        msg = json.loads(raw)

        if msg.get("type") != "auth" or "token" not in msg:
            await websocket.close(code=4001, reason="Invalid auth message")
            return False

        store: RedisSessionStore = app.state.session_store
        expected_token = await store.get_token(session_id)

        if not expected_token or msg["token"] != expected_token:
            await websocket.close(code=4001, reason="Invalid token")
            return False

        return True
    except asyncio.TimeoutError:
        await websocket.close(code=4001, reason="Auth timeout")
        return False
    except (json.JSONDecodeError, KeyError):
        await websocket.close(code=4001, reason="Invalid auth message format")
        return False


async def _send_pipeline_state(websocket: WebSocket, state: str) -> None:
    """Send pipeline state event over WebSocket.

    States: LISTENING, THINKING, SPEAKING
    """
    try:
        await websocket.send_json({"type": "pipeline_state", "state": state})
    except Exception:
        pass


@app.websocket("/ws/call/{session_id}")
async def websocket_call(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time audio/video communication."""
    store: RedisSessionStore = app.state.session_store
    session = await store.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # First-message authentication
    if not await _authenticate_websocket(websocket, session_id):
        return

    # Update session status
    session.status = CallStatus.ACTIVE
    await store.save_session(session)

    # Track active calls
    active_calls.inc()

    # Load pipeline context from Redis
    system_prompt = await store.get_pipeline_context(session_id)
    if not system_prompt:
        await websocket.close(code=4005, reason="Pipeline not initialized")
        active_calls.dec()
        return

    from app.vad import VADProcessor

    http_client = get_http_client()
    pipeline = AIPipeline(system_prompt=system_prompt, http_client=http_client)

    # Load any existing conversation history
    history = await store.get_history(session_id)
    if history:
        pipeline.conversation_history = history

    # Initialize VAD processor for utterance detection
    vad = VADProcessor(
        energy_threshold=settings.vad_energy_threshold,
        silence_duration_ms=settings.vad_silence_duration_ms,
    )

    try:
        while True:
            # Send LISTENING state
            await _send_pipeline_state(websocket, "LISTENING")

            data = await websocket.receive_bytes()

            # Feed audio through VAD - only process complete utterances
            utterance = vad.feed(data)
            if utterance is None:
                # VAD is still collecting audio, wait for more
                continue

            # Send THINKING state
            await _send_pipeline_state(websocket, "THINKING")

            result = await pipeline.process_audio(utterance)

            # Persist updated conversation history
            await store.save_history(session_id, pipeline.conversation_history)

            # Send SPEAKING state
            await _send_pipeline_state(websocket, "SPEAKING")

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
        active_calls.dec()
        session.status = CallStatus.ENDED
        await store.save_session(session)
        await billing_manager.stop_billing_loop(session_id)
        # Cleanup pipeline resources (e.g., Simli session)
        try:
            await pipeline.cleanup()
        except Exception:
            pass
        # Cleanup token
        await store.delete_token(session_id)


@app.websocket("/ws/billing/{session_id}")
async def websocket_billing(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for billing updates.

    Subscribes to Redis pub/sub channel for billing events and forwards
    them to the client. Also starts the billing loop for this session.
    """
    store: RedisSessionStore = app.state.session_store
    session = await store.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    # First-message authentication
    if not await _authenticate_websocket(websocket, session_id):
        return

    # Start billing loop (publishes to Redis pub/sub)
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
    if _shutting_down:
        return {"status": "shutting_down", "service": "ai-astrologer"}
    return {"status": "ok", "service": "ai-astrologer"}

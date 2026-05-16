import asyncio
import json
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import settings
from core.db import async_session_factory, engine
from core.observability import (
    setup_logging,
    setup_sentry,
    CorrelationIdMiddleware,
    metrics_response,
)
from core.api_rate_limiter import RateLimiterMiddleware
from core.graceful_shutdown import GracefulShutdownManager
from channels.email.tracker import router as tracking_router
from dashboard.auth import router as auth_router
from dashboard.routes.campaigns import router as campaigns_router
from dashboard.routes.leads import router as leads_router
from dashboard.routes.sequences import router as sequences_router
from dashboard.routes.analytics import router as analytics_router
from dashboard.routes.optimizer import router as optimizer_router
from dashboard.routes.billing import router as billing_router
from dashboard.routes.whitelabel import router as whitelabel_router
from dashboard.routes.integrations_api import router as integrations_api_router
from dashboard.routes.onboarding import router as onboarding_router
from dashboard.routes.roi import router as roi_router
from dashboard.routes.feedback import router as feedback_router
from dashboard.routes.trial import router as trial_router
from dashboard.routes.preview import router as preview_router
from dashboard.routes.referral import router as referral_router
from dashboard.routes.webhook_status import router as webhook_status_router
from dashboard.routes.crm_webhooks import router as crm_webhooks_router
from dashboard.routes.costs import router as costs_router
from dashboard.routes.reports import router as reports_router
from dashboard.views import router as views_router
from agents.approval_queue import router as approvals_router, set_email_sender
from channels.email.deliverability_routes import router as deliverability_router
from dashboard.routes.voice import router as voice_router
from dashboard.routes.voice_webhooks import router as voice_webhooks_router

# Initialize structured logging
setup_logging()

logger = logging.getLogger(__name__)

_scheduler = None
_inbox_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: startup and shutdown."""
    global _scheduler, _inbox_task

    # Initialize Sentry if DSN is configured
    if settings.sentry_dsn:
        setup_sentry(settings.sentry_dsn)

    # Warn if JWT secret key is still the default insecure value
    if settings.jwt_secret_key == "change-me-in-production":
        logger.warning(
            "JWT_SECRET_KEY is set to the default value 'change-me-in-production'. "
            "This is insecure and must be changed before deploying to production."
        )

    # Startup: initialize scheduler if SMTP domains are configured
    smtp_domains_raw = settings.smtp_domains
    try:
        smtp_accounts = json.loads(smtp_domains_raw)
    except (json.JSONDecodeError, TypeError):
        smtp_accounts = []

    email_sender = None

    if smtp_accounts:
        try:
            from channels.email.sender import AsyncEmailSender
            from channels.email.tracker import EmailTracker
            from channels.email.warmup import DomainWarmupManager
            from agents.copywriter import CopywriterAgent
            from core.llm import LLMClient, FallbackLLMClient
            from scheduler import Scheduler
            from scheduler.sequence_runner import SequenceRunner
            from scheduler.warmup_scheduler import WarmupScheduler

            email_sender = AsyncEmailSender(
                smtp_accounts=smtp_accounts,
                redis_url=settings.redis_url,
            )
            # Register email sender with approval queue for dispatching approved responses
            set_email_sender(email_sender)
            tracker = EmailTracker(
                tracking_base_url=settings.tracking_base_url,
                secret=settings.tracking_secret,
            )
            warmup_manager = DomainWarmupManager(
                redis_url=settings.redis_url,
                domains=[a.get("domain", "") for a in smtp_accounts],
            )

            # Build fallback chain from settings
            _provider_configs = {
                "openai": {
                    "provider": "openai",
                    "api_key": settings.openai_api_key,
                    "model": settings.llm_openai_model,
                    "timeout": settings.llm_openai_timeout,
                },
                "anthropic": {
                    "provider": "anthropic",
                    "api_key": settings.anthropic_api_key,
                    "model": settings.llm_anthropic_model,
                    "timeout": settings.llm_anthropic_timeout,
                },
                "groq": {
                    "provider": "groq",
                    "api_key": settings.groq_api_key,
                    "model": settings.llm_groq_model,
                    "timeout": settings.llm_groq_timeout,
                },
            }
            _chain_names = [
                p.strip()
                for p in settings.llm_fallback_chain.split(",")
                if p.strip()
            ]
            _fallback_providers = [
                _provider_configs[name]
                for name in _chain_names
                if name in _provider_configs
            ]

            llm_client = FallbackLLMClient(
                providers=_fallback_providers,
                redis_url=settings.redis_url,
            )
            copywriter = CopywriterAgent(llm_client=llm_client, settings=settings)

            sequence_runner = SequenceRunner(
                session_factory=async_session_factory,
                redis_url=settings.redis_url,
                email_sender=email_sender,
                copywriter=copywriter,
                tracker=tracker,
            )
            warmup_scheduler = WarmupScheduler(
                warmup_manager=warmup_manager,
                email_sender=email_sender,
                redis_url=settings.redis_url,
            )

            _scheduler = Scheduler(
                sequence_runner=sequence_runner,
                warmup_scheduler=warmup_scheduler,
            )
            await _scheduler.start()
            logger.info("Scheduler started successfully")
        except Exception as exc:
            logger.error("Failed to initialize scheduler: %s", exc)

    # Initialize ConversationAgent and related singletons for webhook use
    try:
        from core.llm import FallbackLLMClient
        from integrations.calendar import CalendarIntegration
        from agents.conversation import ConversationAgent

        # Build fallback chain for webhook LLM client
        _webhook_provider_configs = {
            "openai": {
                "provider": "openai",
                "api_key": settings.openai_api_key,
                "model": settings.llm_openai_model,
                "timeout": settings.llm_openai_timeout,
            },
            "anthropic": {
                "provider": "anthropic",
                "api_key": settings.anthropic_api_key,
                "model": settings.llm_anthropic_model,
                "timeout": settings.llm_anthropic_timeout,
            },
            "groq": {
                "provider": "groq",
                "api_key": settings.groq_api_key,
                "model": settings.llm_groq_model,
                "timeout": settings.llm_groq_timeout,
            },
        }
        _webhook_chain_names = [
            p.strip()
            for p in settings.llm_fallback_chain.split(",")
            if p.strip()
        ]
        _webhook_fallback_providers = [
            _webhook_provider_configs[name]
            for name in _webhook_chain_names
            if name in _webhook_provider_configs
        ]

        webhook_llm_client = FallbackLLMClient(
            providers=_webhook_fallback_providers,
            redis_url=settings.redis_url,
        )
        webhook_calendar = CalendarIntegration(
            provider=settings.calendar_provider,
            api_key=settings.calcom_api_key,
            base_url=settings.calcom_base_url,
        )
        webhook_conversation_agent = ConversationAgent(
            llm_client=webhook_llm_client,
            settings=settings,
            calendar=webhook_calendar,
            session_factory=async_session_factory,
            email_sender=email_sender,
        )

        app.state.llm_client = webhook_llm_client
        app.state.calendar = webhook_calendar
        app.state.conversation_agent = webhook_conversation_agent
    except Exception as exc:
        logger.error("Failed to initialize conversation agent singletons: %s", exc)
        app.state.conversation_agent = None

    # Initialize circuit breaker registry once so /health/detailed shares state
    from core.resilience import CircuitBreakerRegistry

    circuit_breaker_registry = CircuitBreakerRegistry()
    app.state.circuit_breaker_registry = circuit_breaker_registry
    logger.info("Circuit breaker registry initialized")

    # Initialize graceful shutdown manager
    shutdown_manager = GracefulShutdownManager()
    shutdown_manager.register()
    app.state.shutdown_manager = shutdown_manager

    # Health Monitor and Revenue Autopilot
    # These are periodically invoked via asyncio background tasks.
    # Health monitor runs every health_check_interval_minutes.
    # Revenue autopilot runs daily to check lead pools, inactive clients, etc.
    _health_task: asyncio.Task | None = None
    _revenue_task: asyncio.Task | None = None
    _retention_task: asyncio.Task | None = None

    if settings.health_telegram_alerts:
        try:
            from core.health_monitor import HealthMonitor

            health_monitor = HealthMonitor(
                settings=settings,
                session_factory=async_session_factory,
            )
            app.state.health_monitor = health_monitor

            async def _health_loop() -> None:
                interval = settings.health_check_interval_minutes * 60
                while True:
                    try:
                        await health_monitor.run_health_checks()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error("Health check error: %s", exc)
                    await asyncio.sleep(interval)

            _health_task = asyncio.create_task(_health_loop(), name="health_monitor")
            logger.info("Health monitor initialized and scheduled")
        except Exception as exc:
            logger.error("Failed to initialize health monitor: %s", exc)

    try:
        from scheduler.revenue_autopilot import RevenueAutopilot

        revenue_autopilot = RevenueAutopilot(
            session_factory=async_session_factory,
            settings=settings,
        )
        app.state.revenue_autopilot = revenue_autopilot

        async def _revenue_loop() -> None:
            interval = 86400  # Run daily (24 hours)
            while True:
                try:
                    await revenue_autopilot.run_autopilot_tick()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Revenue autopilot error: %s", exc)
                await asyncio.sleep(interval)

        _revenue_task = asyncio.create_task(_revenue_loop(), name="revenue_autopilot")
        logger.info("Revenue autopilot initialized and scheduled")
    except Exception as exc:
        logger.error("Failed to initialize revenue autopilot: %s", exc)

    # Retention engine: run daily retention checks for all active tenants
    try:
        from scheduler.retention import RetentionEngine
        from core.models import Tenant

        retention_engine = RetentionEngine(
            session_factory=async_session_factory,
            settings=settings,
        )
        app.state.retention_engine = retention_engine

        async def _retention_loop() -> None:
            interval = 86400  # Run daily (24 hours)
            while True:
                try:
                    async with async_session_factory() as session:
                        from sqlalchemy import select as _select
                        result = await session.execute(_select(Tenant.id))
                        tenant_ids = [row[0] for row in result.all()]
                    for tid in tenant_ids:
                        try:
                            await retention_engine.run_retention_check(tid)
                        except Exception as exc:
                            logger.error("Retention check error for tenant %s: %s", tid, exc)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Retention engine error: %s", exc)
                await asyncio.sleep(interval)

        _retention_task = asyncio.create_task(_retention_loop(), name="retention_engine")
        logger.info("Retention engine initialized and scheduled")
    except Exception as exc:
        logger.error("Failed to initialize retention engine: %s", exc)

    # Initialize dogfood agent if enabled
    if settings.dogfood_enabled:
        try:
            from agents.dogfood import DogfoodAgent

            dogfood_agent = DogfoodAgent(
                settings=settings,
                session_factory=async_session_factory,
            )
            app.state.dogfood_agent = dogfood_agent
            logger.info("Dogfood agent initialized")
        except Exception as exc:
            logger.error("Failed to initialize dogfood agent: %s", exc)

    # Start InboxListener if IMAP settings are configured
    if settings.imap_host and settings.imap_user and settings.imap_password:
        try:
            from channels.email.inbox import InboxListener

            inbox_listener = InboxListener(
                imap_host=settings.imap_host,
                imap_port=settings.imap_port,
                imap_user=settings.imap_user,
                imap_password=settings.imap_password,
                session_factory=async_session_factory,
            )
            _inbox_task = asyncio.create_task(
                inbox_listener.start_polling(interval_seconds=60)
            )
            logger.info("InboxListener polling started")
        except Exception as exc:
            logger.error("Failed to start InboxListener: %s", exc)

    # Initialize Voice Channel services if Twilio is configured
    _voice_scheduler_task: asyncio.Task | None = None
    if settings.twilio_account_sid:
        try:
            from channels.voice import TwilioClient, DeepgramSTT, ElevenLabsTTS, CallManager
            from scheduler.voice_scheduler import VoiceScheduler
            from agents.voice_conversation import VoiceConversationAgent

            twilio_client = TwilioClient(
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
                from_number=settings.twilio_phone_number,
            )
            deepgram_stt = DeepgramSTT(api_key=settings.deepgram_api_key)
            elevenlabs_tts = ElevenLabsTTS(
                api_key=settings.elevenlabs_api_key,
                voice_id=settings.elevenlabs_voice_id,
            )

            # Use the webhook LLM client already created above
            voice_llm = getattr(app.state, "llm_client", None)

            # Create VoiceConversationAgent for FSM-driven conversations
            voice_agent = VoiceConversationAgent(
                llm_client=voice_llm,
                settings=settings,
                session_factory=async_session_factory,
            )

            call_manager = CallManager(
                twilio_client=twilio_client,
                stt=deepgram_stt,
                tts=elevenlabs_tts,
                llm_client=voice_llm,
                session_factory=async_session_factory,
                settings=settings,
                redis_url=settings.redis_url,
                voice_agent=voice_agent,
            )
            app.state.call_manager = call_manager

            voice_scheduler = VoiceScheduler(
                session_factory=async_session_factory,
                call_manager=call_manager,
                settings=settings,
                redis_url=settings.redis_url,
            )
            app.state.voice_scheduler = voice_scheduler

            async def _voice_scheduler_loop() -> None:
                interval = 60  # Check every 60 seconds
                while True:
                    try:
                        await voice_scheduler.run_voice_tick()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error("Voice scheduler error: %s", exc)
                    await asyncio.sleep(interval)

            _voice_scheduler_task = asyncio.create_task(
                _voice_scheduler_loop(), name="voice_scheduler"
            )
            logger.info("Voice channel services initialized")
        except Exception as exc:
            logger.error("Failed to initialize voice services: %s", exc)

    yield

    # Shutdown
    if _health_task is not None:
        _health_task.cancel()
        try:
            await _health_task
        except asyncio.CancelledError:
            pass
        logger.info("Health monitor stopped")

    if _revenue_task is not None:
        _revenue_task.cancel()
        try:
            await _revenue_task
        except asyncio.CancelledError:
            pass
        logger.info("Revenue autopilot stopped")

    if _retention_task is not None:
        _retention_task.cancel()
        try:
            await _retention_task
        except asyncio.CancelledError:
            pass
        logger.info("Retention engine stopped")

    if _inbox_task is not None:
        _inbox_task.cancel()
        try:
            await _inbox_task
        except asyncio.CancelledError:
            pass
        logger.info("InboxListener stopped")

    if _voice_scheduler_task is not None:
        _voice_scheduler_task.cancel()
        try:
            await _voice_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("Voice scheduler stopped")

    if _scheduler is not None:
        await _scheduler.stop()
        logger.info("Scheduler stopped")

    # Graceful shutdown: wait for in-flight tasks
    await shutdown_manager.shutdown()

    await engine.dispose()


app = FastAPI(
    title="AI Outbound Agency",
    description="Autonomous AI-powered outbound sales agent system",
    version="0.1.0",
    lifespan=lifespan,
)

# Add observability middleware
app.add_middleware(CorrelationIdMiddleware)

# Add API rate limiter middleware (after CorrelationIdMiddleware)
app.add_middleware(RateLimiterMiddleware, redis_url=settings.redis_url)

# Include tracking router for open/click tracking
app.include_router(tracking_router)

# Include dashboard routers
app.include_router(auth_router)
app.include_router(campaigns_router)
app.include_router(leads_router)
app.include_router(sequences_router)
app.include_router(analytics_router)
app.include_router(optimizer_router)
app.include_router(billing_router)
app.include_router(whitelabel_router)
app.include_router(integrations_api_router)
app.include_router(onboarding_router)
app.include_router(roi_router)
app.include_router(feedback_router)
app.include_router(trial_router)
app.include_router(preview_router)
app.include_router(referral_router)
app.include_router(webhook_status_router)
app.include_router(crm_webhooks_router)
app.include_router(costs_router)
app.include_router(reports_router)
app.include_router(approvals_router)
app.include_router(deliverability_router)
app.include_router(voice_router)
app.include_router(voice_webhooks_router)
app.include_router(views_router)

# Mount static files
import os as _os

_static_dir = _os.path.join(_os.path.dirname(__file__), "dashboard", "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


class ReplyWebhookPayload(BaseModel):
    """Payload for the reply webhook endpoint."""
    message_id: str


@app.post("/webhooks/reply")
async def handle_reply_webhook(
    payload: ReplyWebhookPayload,
    request: Request,
) -> JSONResponse:
    """Webhook endpoint for processing inbound replies via ConversationAgent."""
    conversation_agent = getattr(request.app.state, "conversation_agent", None)
    if conversation_agent is None:
        return JSONResponse(
            content={"error": "Conversation agent not initialized"},
            status_code=503,
        )

    try:
        result = await conversation_agent.handle_reply(payload.message_id)
        return JSONResponse(content=result, status_code=200)
    except Exception as exc:
        logger.error("Reply webhook failed: %s", exc)
        return JSONResponse(
            content={"error": str(exc)},
            status_code=500,
        )


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        content={"status": "healthy", "version": "0.1.0"},
        status_code=200,
    )


@app.get("/health/detailed")
async def health_detailed() -> JSONResponse:
    """Detailed health check endpoint with per-service circuit breaker status."""
    from datetime import datetime as _dt, timezone as _tz
    from core.resilience import CircuitBreakerRegistry, CircuitState

    registry = getattr(app.state, "circuit_breaker_registry", None)
    if registry is None:
        # Should not happen since registry is initialized in lifespan,
        # but provide a safe fallback.
        return JSONResponse(
            content={
                "overall_status": "unknown",
                "services": {},
                "timestamp": _dt.now(_tz.utc).isoformat(),
            },
            status_code=503,
        )

    all_status = registry.get_all_status()

    # Determine overall status
    services_output: dict = {}
    has_open = False
    has_degraded = False

    for service_name, status_info in all_status.items():
        state_val = status_info["state"]
        if state_val == CircuitState.OPEN.value:
            has_open = True
            svc_status = "unhealthy"
        elif state_val == CircuitState.HALF_OPEN.value:
            has_degraded = True
            svc_status = "degraded"
        else:
            svc_status = "healthy"

        services_output[service_name] = {
            "status": svc_status,
            "circuit_state": state_val,
        }

    if has_open:
        overall_status = "unhealthy"
    elif has_degraded:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return JSONResponse(
        content={
            "overall_status": overall_status,
            "services": services_output,
            "timestamp": _dt.now(_tz.utc).isoformat(),
        },
        status_code=200,
    )


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus metrics endpoint.

    Protected by METRICS_AUTH_TOKEN when configured. Provide the token
    via the Authorization header as 'Bearer <token>'.
    """
    if settings.metrics_auth_token:
        auth_header = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.metrics_auth_token}"
        if auth_header != expected:
            return Response(content="Unauthorized", status_code=401)
    return metrics_response()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )

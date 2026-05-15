import asyncio
import json
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import settings
from core.db import async_session_factory, engine
from channels.email.tracker import router as tracking_router
from dashboard.auth import router as auth_router
from dashboard.routes.campaigns import router as campaigns_router
from dashboard.routes.leads import router as leads_router
from dashboard.routes.sequences import router as sequences_router
from dashboard.routes.analytics import router as analytics_router
from dashboard.routes.optimizer import router as optimizer_router
from dashboard.views import router as views_router

logger = logging.getLogger(__name__)

_scheduler = None
_inbox_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: startup and shutdown."""
    global _scheduler, _inbox_task

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
            from core.llm import LLMClient
            from scheduler import Scheduler
            from scheduler.sequence_runner import SequenceRunner
            from scheduler.warmup_scheduler import WarmupScheduler

            email_sender = AsyncEmailSender(
                smtp_accounts=smtp_accounts,
                redis_url=settings.redis_url,
            )
            tracker = EmailTracker(
                tracking_base_url=settings.tracking_base_url,
                secret=settings.tracking_secret,
            )
            warmup_manager = DomainWarmupManager(
                redis_url=settings.redis_url,
                domains=[a.get("domain", "") for a in smtp_accounts],
            )

            llm_client = LLMClient(
                provider="openai",
                api_key=settings.openai_api_key,
                model="gpt-4",
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
        from core.llm import LLMClient
        from integrations.calendar import CalendarIntegration
        from agents.conversation import ConversationAgent

        webhook_llm_client = LLMClient(
            provider="openai",
            api_key=settings.openai_api_key,
            model="gpt-4",
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

    yield

    # Shutdown
    if _inbox_task is not None:
        _inbox_task.cancel()
        try:
            await _inbox_task
        except asyncio.CancelledError:
            pass
        logger.info("InboxListener stopped")

    if _scheduler is not None:
        await _scheduler.stop()
        logger.info("Scheduler stopped")

    await engine.dispose()


app = FastAPI(
    title="AI Outbound Agency",
    description="Autonomous AI-powered outbound sales agent system",
    version="0.1.0",
    lifespan=lifespan,
)

# Include tracking router for open/click tracking
app.include_router(tracking_router)

# Include dashboard routers
app.include_router(auth_router)
app.include_router(campaigns_router)
app.include_router(leads_router)
app.include_router(sequences_router)
app.include_router(analytics_router)
app.include_router(optimizer_router)
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )

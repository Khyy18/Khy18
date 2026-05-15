import json
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.db import async_session_factory, engine
from channels.email.tracker import router as tracking_router

logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: startup and shutdown."""
    global _scheduler

    # Startup: initialize scheduler if SMTP domains are configured
    smtp_domains_raw = settings.smtp_domains
    try:
        smtp_accounts = json.loads(smtp_domains_raw)
    except (json.JSONDecodeError, TypeError):
        smtp_accounts = []

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
            tracker = EmailTracker(tracking_base_url=settings.tracking_base_url)
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

    yield

    # Shutdown
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


class ReplyWebhookPayload(BaseModel):
    """Payload for the reply webhook endpoint."""
    message_id: str


@app.post("/webhooks/reply")
async def handle_reply_webhook(payload: ReplyWebhookPayload) -> JSONResponse:
    """Webhook endpoint for processing inbound replies via ConversationAgent."""
    from agents.conversation import ConversationAgent
    from core.llm import LLMClient
    from integrations.calendar import CalendarIntegration

    llm_client = LLMClient(
        provider="openai",
        api_key=settings.openai_api_key,
        model="gpt-4",
    )
    calendar = CalendarIntegration(
        provider=settings.calendar_provider,
        api_key=settings.calcom_api_key,
        base_url=settings.calcom_base_url,
    )
    conversation_agent = ConversationAgent(
        llm_client=llm_client,
        settings=settings,
        calendar=calendar,
        session_factory=async_session_factory,
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

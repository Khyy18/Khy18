"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.routers import alerts, categories, deals, favorites, profile
from app.routers import payments, tracking, chatbot
from app.services.parser_monitor import parser_monitor
from app.services.proxy_pool import proxy_pool

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()

    # Load proxies and start background scheduler
    proxy_pool.load_proxies()

    scheduler.add_job(proxy_pool.health_check, "interval", minutes=5, id="proxy_health")
    scheduler.add_job(parser_monitor.check_parsers, "interval", minutes=15, id="parser_monitor")
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Price Monitor API",
    description="Backend API for the Price Monitor mobile app",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deals.router)
app.include_router(categories.router)
app.include_router(alerts.router)
app.include_router(favorites.router)
app.include_router(profile.router)
app.include_router(payments.router)
app.include_router(tracking.router)
app.include_router(chatbot.router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/admin/parser-status", tags=["admin"])
async def parser_status():
    """Get current parser data freshness status."""
    result = await parser_monitor.check_parsers()
    return result

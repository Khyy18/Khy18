"""FastAPI application entry point."""
from __future__ import annotations


from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.redis_client import close_redis
from app.db.session import init_db
from app.routers import (
    admin,
    alerts,
    arbitrage,
    auth,
    categories,
    chatbot,
    compare,
    content,
    deals,
    favorites,
    onboarding,
    partners,
    payments,
    profile,
    support,
    tracking,
    websocket,
)

# Initialize Sentry
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.2,
        profiles_sample_rate=0.1,
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    yield
    await close_redis()

app = FastAPI(
    title="Price Monitor WebApp API",
    description="Backend API для мониторинга цен на маркетплейсах",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth.router)
app.include_router(deals.router)
app.include_router(compare.router)
app.include_router(categories.router)
app.include_router(alerts.router)
app.include_router(favorites.router)
app.include_router(profile.router)
app.include_router(payments.router)
app.include_router(tracking.router)
app.include_router(chatbot.router)
app.include_router(arbitrage.router)
app.include_router(admin.router)
app.include_router(content.router)
app.include_router(partners.router)
app.include_router(websocket.router)
app.include_router(support.router)
app.include_router(onboarding.router)

@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

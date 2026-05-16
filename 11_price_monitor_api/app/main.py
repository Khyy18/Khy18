"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.routers import alerts, categories, deals, favorites, profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    yield


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


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

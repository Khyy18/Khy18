"""One-time download links endpoint."""

import asyncio
import base64
import io
import time
import uuid
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.auth import verify_bearer_token

router = APIRouter(prefix="/downloads", tags=["downloads"])

# In-memory store for download tokens
_download_store: Dict[str, dict] = {}

# Expiry time in seconds
DOWNLOAD_EXPIRY_SECONDS = 600  # 10 minutes


class DownloadCreateRequest(BaseModel):
    """Request to create a one-time download link."""
    content_base64: str = Field(..., description="Base64-encoded file content")
    filename: str = Field(..., min_length=1, max_length=255)


class DownloadCreateResponse(BaseModel):
    """Response with the generated download link."""
    token: str
    url: str
    expires_at: float


@router.post("/create", response_model=DownloadCreateResponse)
async def create_download(
    data: DownloadCreateRequest,
    _token: str = Depends(verify_bearer_token),
):
    """Create a one-time download link for a file."""
    token = str(uuid.uuid4())
    expires_at = time.time() + DOWNLOAD_EXPIRY_SECONDS

    _download_store[token] = {
        "content": data.content_base64,
        "filename": data.filename,
        "expires_at": expires_at,
    }

    return DownloadCreateResponse(
        token=token,
        url=f"/api/v1/downloads/{token}",
        expires_at=expires_at,
    )


@router.get("/{token}")
async def download_file(token: str):
    """Download file once, then delete the token."""
    entry = _download_store.get(token)

    if entry is None:
        raise HTTPException(status_code=404, detail="Download link not found or expired")

    if time.time() > entry["expires_at"]:
        del _download_store[token]
        raise HTTPException(status_code=404, detail="Download link expired")

    # Remove from store (one-time use)
    del _download_store[token]

    content = base64.b64decode(entry["content"])
    buffer = io.BytesIO(content)

    return StreamingResponse(
        buffer,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={entry['filename']}"},
    )


async def _cleanup_expired():
    """Background task to clean up expired tokens."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired = [k for k, v in _download_store.items() if now > v["expires_at"]]
        for k in expired:
            _download_store.pop(k, None)

"""Content router - video script generation API."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.services.content_generator import content_generator

router = APIRouter(prefix="/content", tags=["content"])

@router.post("/video-script")
async def generate_video_script(
    product_id: int,
    script_type: str = "review",
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Generate a video script for a product."""

    result = await content_generator.generate_script(
        product_id=product_id,
        script_type=script_type,
        db=db,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return result

@router.get("/scripts/{product_id}")
async def get_scripts(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get all generated scripts for a product."""
    from sqlalchemy import select
    from app.db.models import ContentScript

    result = await db.execute(
        select(ContentScript)
        .where(ContentScript.product_id == product_id)
        .order_by(ContentScript.created_at.desc())
    )
    scripts = result.scalars().all()
    return [
        {
            "id": s.id,
            "script_type": s.script_type,
            "content": s.content,
            "created_at": s.created_at.isoformat(),
        }
        for s in scripts
    ]

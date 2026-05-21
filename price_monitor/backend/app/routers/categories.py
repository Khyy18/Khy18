"""Categories router - categories with product counts."""
from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product, User
from app.db.redis_client import cache_get, cache_set
from app.db.session import get_db
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("")
async def get_categories(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get all categories with product counts."""

    cache_key = "categories:all"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    query = (
        select(Product.category, func.count(Product.id).label("count"))
        .where(Product.category.isnot(None))
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
    )
    result = await db.execute(query)
    rows = result.all()

    categories = [
        {"name": row.category, "count": row.count}
        for row in rows
    ]

    await cache_set(cache_key, categories, ttl=300)
    return categories

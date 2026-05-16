"""Deals router - paginated product listings with Redis caching."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product, User
from app.db.redis_client import cache_get, cache_set
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.deals import DealListResponse, DealOut, PricePointOut

router = APIRouter(prefix="/deals", tags=["deals"])

def _product_to_deal(product: Product) -> DealOut:
    """Convert a Product ORM model to DealOut schema."""

    latest_price = None
    if product.price_history:
        latest_price = sorted(product.price_history, key=lambda p: p.timestamp, reverse=True)[0]

    return DealOut(
        id=str(product.id),
        title=product.name,
        image=product.image_url or "",
        currentPrice=latest_price.price if latest_price else 0.0,
        oldPrice=latest_price.old_price or 0.0 if latest_price else 0.0,
        discount=latest_price.discount_percent or 0.0 if latest_price else 0.0,
        category=product.category or "",
        marketplace=product.marketplace,
        priceHistory=[
            PricePointOut(date=ph.timestamp.isoformat(), price=ph.price)
            for ph in sorted(product.price_history, key=lambda p: p.timestamp)
        ],
        rating=product.rating or 0.0,
        reviewsSummary=product.reviews_summary or "",
        affiliateUrl=product.url or "",
        forecast=None,
    )

@router.get("", response_model=DealListResponse)
async def get_deals(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    category: str | None = None,
    marketplace: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get paginated list of deals with optional filters."""
    cache_key = f"deals:{category}:{marketplace}:{page}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return DealListResponse(**cached)

    query = select(Product).options(selectinload(Product.price_history))
    count_query = select(func.count(Product.id))

    if category:
        query = query.where(Product.category == category)
        count_query = count_query.where(Product.category == category)
    if marketplace:
        query = query.where(Product.marketplace == marketplace)
        count_query = count_query.where(Product.marketplace == marketplace)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()

    deals = [_product_to_deal(p) for p in products]
    has_more = (offset + limit) < total

    response = DealListResponse(products=deals, total=total, hasMore=has_more)
    await cache_set(cache_key, response.model_dump(), ttl=120)
    return response

@router.get("/{deal_id}", response_model=DealOut)
async def get_deal_by_id(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get a single deal by ID with full price history."""
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.price_history))
        .where(Product.id == deal_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return _product_to_deal(product)

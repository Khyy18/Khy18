"""Favorites router - add/remove favorites."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Favorite, Product, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.deals import DealOut, PricePointOut

router = APIRouter(prefix="/favorites", tags=["favorites"])

@router.get("")
async def get_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all favorites for the current user."""

    result = await db.execute(
        select(Favorite)
        .options(selectinload(Favorite.product).selectinload(Product.price_history))
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    favorites = result.scalars().all()

    items = []
    for fav in favorites:
        p = fav.product
        latest_price = None
        if p.price_history:
            latest_price = sorted(p.price_history, key=lambda ph: ph.timestamp, reverse=True)[0]
        items.append(
            DealOut(
                id=str(p.id),
                title=p.name,
                image=p.image_url or "",
                currentPrice=latest_price.price if latest_price else 0.0,
                oldPrice=latest_price.old_price or 0.0 if latest_price else 0.0,
                discount=latest_price.discount_percent or 0.0 if latest_price else 0.0,
                category=p.category or "",
                marketplace=p.marketplace,
                priceHistory=[
                    PricePointOut(date=ph.timestamp.isoformat(), price=ph.price)
                    for ph in sorted(p.price_history, key=lambda ph: ph.timestamp)
                ],
                rating=p.rating or 0.0,
                reviewsSummary=p.reviews_summary or "",
                affiliateUrl=p.url or "",
            )
        )
    return items

@router.post("/{product_id}")
async def add_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add product to favorites."""
    # Check product exists
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Check if already favorited
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.product_id == product_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Уже в избранном")

    fav = Favorite(user_id=user.id, product_id=product_id)
    db.add(fav)
    await db.commit()
    return {"ok": True}

@router.delete("/{product_id}")
async def remove_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove product from favorites."""
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.product_id == product_id
        )
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Не найдено в избранном")
    await db.delete(fav)
    await db.commit()
    return {"ok": True}

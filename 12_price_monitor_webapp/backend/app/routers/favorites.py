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
                image_url=p.image_url or "",
                current_price=latest_price.price if latest_price else 0.0,
                original_price=latest_price.old_price or 0.0 if latest_price else 0.0,
                discount_percent=latest_price.discount_percent or 0.0 if latest_price else 0.0,
                marketplace=p.marketplace,
                category_id=p.category or "",
                category_name=p.category or "",
                url=p.url or "",
                price_history=[
                    PricePointOut(date=ph.timestamp.isoformat(), price=ph.price)
                    for ph in sorted(p.price_history, key=lambda ph: ph.timestamp)
                ],
                is_favorite=True,
                created_at=p.created_at.isoformat() if p.created_at else "",
                rating=p.rating or 0.0,
                reviews_summary=p.reviews_summary or "",
            )
        )
    return items

@router.post("/{product_id}")
async def toggle_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Toggle product in favorites. Returns current favorite state."""
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
    fav = existing.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()
        return {"is_favorite": False}

    new_fav = Favorite(user_id=user.id, product_id=product_id)
    db.add(new_fav)
    await db.commit()
    return {"is_favorite": True}

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
    return {"is_favorite": False}

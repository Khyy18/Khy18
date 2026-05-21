"""Favorites router - manage user's favorite products."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Favorite, Product, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.deals import DealOut, PricePointOut

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=list[DealOut])
async def get_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get user's favorited products."""
    result = await db.execute(
        select(Favorite)
        .where(Favorite.user_id == user.id)
        .options(selectinload(Favorite.product).selectinload(Product.price_history))
    )
    favorites = result.scalars().all()

    deals = []
    for fav in favorites:
        product = fav.product
        latest_price = None
        if product.price_history:
            latest_price = sorted(product.price_history, key=lambda p: p.timestamp, reverse=True)[0]

        deals.append(DealOut(
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
        ))
    return deals


@router.post("/{product_id}", status_code=201)
async def add_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a product to favorites."""
    # Check product exists
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check not already favorited
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.product_id == product_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already in favorites")

    favorite = Favorite(user_id=user.id, product_id=product_id)
    db.add(favorite)
    await db.commit()
    return {"status": "added"}


@router.delete("/{product_id}", status_code=204)
async def remove_favorite(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a product from favorites."""
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.product_id == product_id
        )
    )
    favorite = result.scalar_one_or_none()
    if not favorite:
        raise HTTPException(status_code=404, detail="Not in favorites")
    await db.delete(favorite)
    await db.commit()

"""Compare products endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Product, User
from app.db.session import get_db
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("/compare")
async def compare_products(
    ids: str = Query(..., description="Comma-separated product IDs"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Compare 2 products side by side."""
    try:
        id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "Invalid product IDs format")

    if len(id_list) < 2:
        raise HTTPException(400, "Need at least 2 product IDs")

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.price_history))
        .where(Product.id.in_(id_list[:2]))
    )
    products = result.scalars().all()
    if len(products) < 2:
        raise HTTPException(404, "Products not found")

    def serialize_product(p: Product) -> dict:
        history = sorted(p.price_history, key=lambda h: h.timestamp)
        latest = history[-1] if history else None
        current_price = latest.price if latest else 0.0
        original_price = latest.old_price if latest and latest.old_price else current_price
        discount = (
            round((1 - current_price / original_price) * 100, 1)
            if original_price > 0 and current_price < original_price
            else 0.0
        )
        return {
            "id": str(p.id),
            "title": p.name,
            "image_url": p.image_url or "",
            "current_price": current_price,
            "original_price": original_price,
            "discount_percent": discount,
            "marketplace": p.marketplace,
            "rating": p.rating or 0.0,
            "price_history": [
                {"date": h.timestamp.isoformat(), "price": h.price}
                for h in history
            ],
        }

    return {
        "products": [serialize_product(p) for p in products]
    }

"""Categories router."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.categories import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def get_categories(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get all categories with product counts."""
    result = await db.execute(
        select(Product.category, func.count(Product.id))
        .where(Product.category.isnot(None))
        .group_by(Product.category)
    )
    rows = result.all()

    categories = []
    for i, (name, count) in enumerate(rows):
        categories.append(
            CategoryOut(
                id=str(i + 1),
                name=name or "Other",
                icon="tag",
                productCount=count,
            )
        )
    return categories

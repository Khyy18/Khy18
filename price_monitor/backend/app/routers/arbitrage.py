"""Arbitrage router - price arbitrage between WB and Ozon."""
from __future__ import annotations


from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArbitrageResult, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.arbitrage import ArbitrageListResponse, ArbitrageResultOut, ArbitrageSearchRequest
from app.services.arbitrage_service import arbitrage_service

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])

@router.get("", response_model=ArbitrageListResponse)
async def get_arbitrage_results(
    category: str | None = None,
    min_diff: float = Query(5.0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get arbitrage results (price differences between WB and Ozon)."""

    query = select(ArbitrageResult).order_by(ArbitrageResult.diff_percent.desc())

    if min_diff > 0:
        query = query.where(ArbitrageResult.diff_percent >= min_diff)

    query = query.limit(limit)
    result = await db.execute(query)
    rows = result.scalars().all()

    items = [
        ArbitrageResultOut(
            id=r.id,
            product_name=r.product_name,
            brand=r.brand,
            price_wb=r.price_wb,
            price_ozon=r.price_ozon,
            diff_percent=r.diff_percent,
            match_score=r.match_score,
            found_at=r.found_at.isoformat(),
        )
        for r in rows
    ]
    return ArbitrageListResponse(results=items, total=len(items))

@router.post("/scan")
async def trigger_arbitrage_scan(
    data: ArbitrageSearchRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Trigger a new arbitrage scan."""
    count = await arbitrage_service.scan(
        category=data.category,
        min_diff_percent=data.min_diff_percent,
        limit=data.limit,
        db=db,
    )
    return {"scanned": count, "message": f"Найдено {count} расхождений в ценах"}

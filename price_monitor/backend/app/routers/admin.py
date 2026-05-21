"""Admin router - admin dashboard API (stats, users, posts, parsers, settings)."""
from __future__ import annotations


from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, Click, Payment, Post, Product, User
from app.db.session import get_db
from app.middleware.auth import get_admin_user
from app.schemas.admin import (
    AnalyticsOut,
    DayMetricOut,
    MonthRevenueOut,
    PostCreate,
    PostOut,
    StatsOut,
    UserAdminOut,
)
from app.services.parser_monitor import parser_monitor

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/stats", response_model=StatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Get dashboard statistics."""

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    vip_users = (
        await db.execute(select(func.count(User.id)).where(User.is_vip == True))
    ).scalar() or 0
    total_products = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    total_alerts = (await db.execute(select(func.count(Alert.id)))).scalar() or 0
    total_clicks = (await db.execute(select(func.count(Click.id)))).scalar() or 0
    total_revenue = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0.0)).where(
                Payment.status == "confirmed"
            )
        )
    ).scalar() or 0.0

    return StatsOut(
        total_users=total_users,
        vip_users=vip_users,
        total_products=total_products,
        total_alerts=total_alerts,
        total_clicks=total_clicks,
        total_revenue=total_revenue,
    )

@router.get("/users", response_model=list[UserAdminOut])
async def get_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Get paginated list of users."""
    offset = (page - 1) * limit
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()
    return [
        UserAdminOut(
            id=u.id,
            telegram_id=u.telegram_id,
            username=u.username,
            is_vip=u.is_vip,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]

@router.get("/posts", response_model=list[PostOut])
async def get_posts(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Get recent posts."""
    result = await db.execute(
        select(Post).order_by(Post.published_at.desc()).limit(limit)
    )
    posts = result.scalars().all()
    return [
        PostOut(
            id=p.id,
            product_id=p.product_id,
            channel_id=p.channel_id,
            text=p.text,
            variant=p.variant,
            impressions=p.impressions,
            clicks=p.clicks,
            ctr=p.ctr,
            published_at=p.published_at.isoformat(),
        )
        for p in posts
    ]

@router.post("/posts", response_model=PostOut)
async def create_post(
    data: PostCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Create a new post."""
    post = Post(
        product_id=data.product_id,
        channel_id=data.channel_id,
        text=data.text,
        variant=data.variant,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return PostOut(
        id=post.id,
        product_id=post.product_id,
        channel_id=post.channel_id,
        text=post.text,
        variant=post.variant,
        impressions=post.impressions,
        clicks=post.clicks,
        ctr=post.ctr,
        published_at=post.published_at.isoformat(),
    )

@router.get("/parsers")
async def get_parser_status(
    _admin: User = Depends(get_admin_user),
):
    """Get parser health status."""
    result = await parser_monitor.check_parsers()
    return result

@router.get("/analytics", response_model=AnalyticsOut)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Get time-series analytics data for dashboard charts."""

    # Clicks and conversions by day for last 7 days
    today = date.today()
    week_ago = today - timedelta(days=6)

    clicks_query = (
        select(
            cast(Click.timestamp, Date).label("day"),
            func.count(Click.id).label("clicks"),
            func.count(func.nullif(Click.converted, False)).label("conversions"),
        )
        .where(cast(Click.timestamp, Date) >= week_ago)
        .group_by(cast(Click.timestamp, Date))
        .order_by(cast(Click.timestamp, Date))
    )
    clicks_result = await db.execute(clicks_query)
    clicks_rows = clicks_result.all()

    # Build map of day -> metrics
    day_map: dict[str, tuple[int, int]] = {}
    for row in clicks_rows:
        day_map[str(row.day)] = (row.clicks, row.conversions)

    clicks_by_day: list[DayMetricOut] = []
    for i in range(7):
        d = week_ago + timedelta(days=i)
        day_str = str(d)
        clicks_count, conv_count = day_map.get(day_str, (0, 0))
        clicks_by_day.append(
            DayMetricOut(date=day_str, clicks=clicks_count, conversions=conv_count)
        )

    # Revenue by month for last 6 months
    month_names = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    revenue_by_month: list[MonthRevenueOut] = []

    for i in range(5, -1, -1):
        # Calculate month start/end
        month_offset = today.month - 1 - i
        year = today.year + (month_offset // 12)
        month = (month_offset % 12) + 1
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1)
        else:
            month_end = date(year, month + 1, 1)

        rev_query = select(
            func.coalesce(func.sum(Payment.amount), 0.0)
        ).where(
            Payment.status == "confirmed",
            cast(Payment.created_at, Date) >= month_start,
            cast(Payment.created_at, Date) < month_end,
        )
        rev_result = await db.execute(rev_query)
        total_rev = rev_result.scalar() or 0.0

        revenue_by_month.append(
            MonthRevenueOut(month=month_names[month - 1], revenue=float(total_rev))
        )

    return AnalyticsOut(
        clicks_by_day=clicks_by_day,
        revenue_by_month=revenue_by_month,
    )

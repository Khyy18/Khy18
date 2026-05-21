"""Push notification service with user profiling and FCM delivery."""

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Click, Favorite, Product, PushLog, User

logger = logging.getLogger(__name__)


class PushService:
    """Service for behavior-based push notifications via FCM."""

    async def build_user_profile(
        self, user_id: int, db: AsyncSession
    ) -> dict:
        """Analyze user clicks and favorites to build interest profile.

        Returns dict with top_categories (list[str]) and avg_price_range (tuple).
        """
        # Get categories from favorites
        fav_result = await db.execute(
            select(Product.category, Product.id)
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.user_id == user_id)
        )
        fav_rows = fav_result.all()

        # Get categories from clicks
        click_result = await db.execute(
            select(Product.category, Product.id)
            .join(Click, Click.product_id == Product.id)
            .where(Click.user_id == user_id)
        )
        click_rows = click_result.all()

        # Count category occurrences
        category_counts: dict[str, int] = {}
        for row in list(fav_rows) + list(click_rows):
            cat = row[0]
            if cat:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        # Sort by frequency, take top 5
        top_categories = sorted(category_counts, key=category_counts.get, reverse=True)[:5]

        # Calculate average price range from favorites
        price_result = await db.execute(
            select(func.min(Product.rating), func.max(Product.rating))
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.user_id == user_id)
        )
        # Use click prices for range estimation
        from app.db.models import PriceHistory

        prices_result = await db.execute(
            select(PriceHistory.price)
            .join(Favorite, Favorite.product_id == PriceHistory.product_id)
            .where(Favorite.user_id == user_id)
            .order_by(PriceHistory.timestamp.desc())
            .limit(50)
        )
        prices = [row[0] for row in prices_result.all()]

        if prices:
            avg_min = min(prices) * 0.8
            avg_max = max(prices) * 1.2
        else:
            avg_min = 0.0
            avg_max = 100000.0

        return {
            "top_categories": top_categories,
            "avg_price_range": (avg_min, avg_max),
        }

    async def should_push(
        self, user_id: int, product: Product, db: AsyncSession
    ) -> bool:
        """Check if a push should be sent for this user+product combination.

        Returns True if product matches user profile AND user has < 3 pushes today.
        """
        profile = await self.build_user_profile(user_id, db)

        # Check category match
        product_category = product.category or ""
        if profile["top_categories"] and product_category not in profile["top_categories"]:
            return False

        # Check price range (use latest price)
        if product.price_history:
            latest = sorted(product.price_history, key=lambda p: p.timestamp, reverse=True)[0]
            price = latest.price
            min_price, max_price = profile["avg_price_range"]
            if price < min_price or price > max_price:
                return False

        # Check daily push limit (< 3 pushes today)
        # Uses dedicated PushLog table to avoid polluting chat history
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        push_count_result = await db.execute(
            select(func.count(PushLog.id)).where(
                PushLog.user_id == user_id,
                PushLog.sent_at >= today_start,
            )
        )
        push_count = push_count_result.scalar() or 0

        return push_count < 3

    async def send_push(
        self, user_id: int, title: str, body: str, db: AsyncSession
    ) -> bool:
        """Send FCM push notification to user.

        Args:
            user_id: Target user ID.
            title: Notification title.
            body: Notification body text.
            db: Database session.

        Returns:
            True if sent successfully, False otherwise.
        """
        # Get user FCM token
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.fcm_token:
            logger.warning("No FCM token for user %d", user_id)
            return False

        if not settings.fcm_server_key:
            logger.warning("FCM server key not configured")
            return False

        payload = {
            "to": user.fcm_token,
            "notification": {
                "title": title,
                "body": body,
            },
        }

        try:
            # TODO: Migrate to FCM HTTP v1 API (https://firebase.google.com/docs/cloud-messaging/migrate-v1).
            # The legacy endpoint (fcm.googleapis.com/fcm/send) is deprecated and will be removed.
            # Migration requires: service account JSON key, OAuth2 token generation,
            # and new endpoint: https://fcm.googleapis.com/v1/projects/{project_id}/messages:send
            # Current implementation still works but should be updated before June 2024 deadline.
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    json=payload,
                    headers={
                        "Authorization": f"key={settings.fcm_server_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )
                if response.status_code == 200:
                    # Record push in dedicated PushLog table
                    push_log = PushLog(
                        user_id=user_id,
                        title=title,
                        body=body,
                    )
                    db.add(push_log)
                    await db.commit()
                    return True
                else:
                    logger.error("FCM send failed: %d %s", response.status_code, response.text)
                    return False
        except Exception as e:
            logger.error("FCM send error: %s", e)
            return False

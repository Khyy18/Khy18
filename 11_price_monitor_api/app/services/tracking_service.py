"""Short link generation and click tracking service."""

import string
import secrets
from datetime import datetime

from sqlalchemy import Integer, select, func, cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Click, Product

BASE62_CHARS = string.ascii_letters + string.digits
SHORT_ID_LENGTH = 8

# In-memory mapping of short_id -> {affiliate_url, product_id}
# In production, this would be a DB table; for this implementation,
# we store the mapping alongside Click records and use in-memory cache.
_short_links: dict[str, dict] = {}


class TrackingService:
    """Generates short links and records click events."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _generate_short_id() -> str:
        """Generate a random 8-character base62 short ID."""
        return "".join(secrets.choice(BASE62_CHARS) for _ in range(SHORT_ID_LENGTH))

    def create_short_link(self, product_id: int, affiliate_url: str) -> str:
        """Create a short link mapping and return the short_id."""
        short_id = self._generate_short_id()
        _short_links[short_id] = {
            "product_id": product_id,
            "affiliate_url": affiliate_url,
        }
        return short_id

    @staticmethod
    def resolve_short_link(short_id: str) -> dict | None:
        """Resolve a short_id to its target URL and product_id."""
        return _short_links.get(short_id)

    async def record_click(
        self,
        short_id: str,
        user_id: int | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Record a click event for a short link."""
        link_data = _short_links.get(short_id)
        if not link_data:
            return

        click = Click(
            short_id=short_id,
            product_id=link_data["product_id"],
            user_id=user_id,
            ip=ip,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
        )
        self.db.add(click)
        await self.db.commit()

    async def get_stats(self) -> list[dict]:
        """Get click statistics grouped by product."""
        result = await self.db.execute(
            select(
                Click.short_id,
                Click.product_id,
                func.count(Click.id).label("total_clicks"),
                func.count(func.distinct(Click.user_id)).label("unique_users"),
                func.sum(cast(Click.converted, Integer)).label("conversions"),
            )
            .group_by(Click.short_id, Click.product_id)
        )
        rows = result.all()

        stats = []
        for row in rows:
            total = row.total_clicks or 0
            conversions = row.conversions or 0
            ctr = (conversions / total * 100) if total > 0 else 0.0
            stats.append({
                "short_id": row.short_id,
                "product_id": row.product_id,
                "total_clicks": total,
                "unique_users": row.unique_users or 0,
                "conversions": conversions,
                "ctr": round(ctr, 2),
            })

        return stats

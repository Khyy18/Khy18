"""Parser monitor service - parser health checks."""
from __future__ import annotations


import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.models import Product

logger = logging.getLogger(__name__)

class ParserMonitor:
    """Monitors parser health by checking data freshness."""

    PARSERS = [
        {"name": "Wildberries", "marketplace": "wb"},
        {"name": "Ozon", "marketplace": "ozon"},
    ]

    async def check_parsers(self) -> list[dict]:
        """Check data freshness for each parser/marketplace."""
        from app.db.session import async_session

        results = []
        async with async_session() as db:
            for parser in self.PARSERS:
                result = await db.execute(
                    select(
                        func.count(Product.id),
                        func.max(Product.created_at),
                    ).where(Product.marketplace == parser["marketplace"])
                )
                row = result.one()
                count = row[0] or 0
                last_run = row[1]

                status = "ok"
                if count == 0:
                    status = "no_data"
                elif last_run:
                    age = (datetime.now(timezone.utc) - last_run).total_seconds()
                    if age > 3600:
                        status = "stale"

                results.append({
                    "name": parser["name"],
                    "marketplace": parser["marketplace"],
                    "status": status,
                    "products_count": count,
                    "last_run": last_run.isoformat() if last_run else None,
                })

        return results

parser_monitor = ParserMonitor()

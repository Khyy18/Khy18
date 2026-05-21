"""Parser monitoring service with Telegram alerts."""

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PriceHistory
from app.db.session import async_session

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
STALE_THRESHOLD_MINUTES = 60


class ParserMonitor:
    """Monitors parser freshness and sends Telegram alerts if data is stale."""

    def __init__(self, bot_token: str = "", admin_chat_id: int = 0):
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id or settings.telegram_admin_id

    async def get_last_data_time(self, db: AsyncSession) -> datetime | None:
        """Get the timestamp of the most recent price_history entry."""
        result = await db.execute(
            select(PriceHistory.timestamp)
            .order_by(PriceHistory.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def check_parsers(self) -> dict:
        """Check if parsers are producing fresh data.

        Returns status dict and sends alert if stale.
        """
        async with async_session() as db:
            last_time = await self.get_last_data_time(db)

        now = datetime.utcnow()

        if last_time is None:
            status = "dead"
            staleness_minutes = -1
        else:
            delta = now - last_time
            staleness_minutes = int(delta.total_seconds() / 60)
            if staleness_minutes > STALE_THRESHOLD_MINUTES:
                status = "stale"
            else:
                status = "ok"

        result = {
            "last_data_time": last_time.isoformat() if last_time else None,
            "status": status,
            "staleness_minutes": staleness_minutes,
        }

        if status in ("stale", "dead"):
            await self._send_alert(result)

        return result

    async def _send_alert(self, status_info: dict) -> None:
        """Send Telegram alert to admin about stale parser data."""
        if not self.bot_token or not self.admin_chat_id:
            logger.warning("Telegram alert skipped: bot_token or admin_id not set")
            return

        text = (
            f"⚠️ Parser Monitor Alert\n\n"
            f"Status: {status_info['status']}\n"
            f"Last data: {status_info['last_data_time'] or 'never'}\n"
            f"Staleness: {status_info['staleness_minutes']} min"
        )

        url = TELEGRAM_API_URL.format(token=self.bot_token)
        payload = {
            "chat_id": self.admin_chat_id,
            "text": text,
        }

        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, timeout=10.0)
        except Exception as e:
            logger.error("Failed to send Telegram alert: %s", e)


# Module-level singleton
parser_monitor = ParserMonitor()

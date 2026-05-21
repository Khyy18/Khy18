"""Tracking service - click/conversion tracking."""
from __future__ import annotations


import secrets
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Click, Partner, ShortLink

logger = logging.getLogger(__name__)

class TrackingService:
    """Manages short links and click/conversion tracking."""

    async def create_short_link(
        self,
        product_id: int,
        affiliate_url: str,
        db: AsyncSession,
        partner_id: int | None = None,
    ) -> ShortLink:
        """Create a new short tracking link."""
        short_id = secrets.token_urlsafe(8)
        link = ShortLink(
            short_id=short_id,
            product_id=product_id,
            affiliate_url=affiliate_url,
            partner_id=partner_id,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)
        return link

    async def mark_conversion(self, short_id: str, db: AsyncSession) -> None:
        """Mark the latest click for a short link as converted."""
        result = await db.execute(
            select(Click)
            .where(Click.short_id == short_id, Click.converted == False)
            .order_by(Click.timestamp.desc())
            .limit(1)
        )
        click = result.scalar_one_or_none()
        if click:
            click.converted = True

            # Update partner stats if applicable
            if click.partner_id:
                result = await db.execute(
                    select(Partner).where(Partner.id == click.partner_id)
                )
                partner = result.scalar_one_or_none()
                if partner:
                    partner.total_conversions += 1

            await db.commit()

tracking_service = TrackingService()

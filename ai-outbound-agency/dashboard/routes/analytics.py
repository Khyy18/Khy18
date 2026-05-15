from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Campaign,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Sequence,
    User,
)
from dashboard.auth import get_current_user
from dashboard.schemas import (
    CampaignStatsResponse,
    FunnelResponse,
    TimelineDataPoint,
    TimelineResponse,
    TopSequenceItem,
    TopSequencesResponse,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.get("/funnel", response_model=FunnelResponse)
async def get_funnel(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    result = await session.execute(
        select(Lead.status, func.count())
        .where(Lead.tenant_id == current_user.tenant_id)
        .group_by(Lead.status)
    )
    funnel = {str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1] for row in result.all()}
    return {"funnel": funnel}


@router.get("/campaign/{campaign_id}/stats", response_model=CampaignStatsResponse)
async def get_campaign_stats(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    # Verify campaign belongs to tenant
    campaign_result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = campaign_result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Total leads (distinct leads with messages in this campaign)
    total_leads_result = await session.execute(
        select(func.count(func.distinct(Message.lead_id))).where(
            Message.campaign_id == campaign_id
        )
    )
    total_leads = total_leads_result.scalar() or 0

    # Messages sent
    messages_sent_result = await session.execute(
        select(func.count()).select_from(Message).where(
            Message.campaign_id == campaign_id,
            Message.status != MessageStatus.draft,
        )
    )
    messages_sent = messages_sent_result.scalar() or 0

    if messages_sent == 0:
        return {
            "total_leads": total_leads,
            "messages_sent": 0,
            "open_rate": 0.0,
            "click_rate": 0.0,
            "reply_rate": 0.0,
            "book_rate": 0.0,
        }

    # Count events by type for messages in this campaign
    event_counts_result = await session.execute(
        select(Event.event_type, func.count())
        .join(Message, Event.message_id == Message.id)
        .where(Message.campaign_id == campaign_id)
        .group_by(Event.event_type)
    )
    event_counts = {row[0]: row[1] for row in event_counts_result.all()}

    opens = event_counts.get(EventType.open, 0)
    clicks = event_counts.get(EventType.click, 0)
    replies = event_counts.get(EventType.reply, 0)

    # Book rate from leads with status=booked in this campaign
    booked_result = await session.execute(
        select(func.count(func.distinct(Lead.id)))
        .join(Message, Message.lead_id == Lead.id)
        .where(
            Message.campaign_id == campaign_id,
            Lead.status == LeadStatus.booked,
        )
    )
    booked = booked_result.scalar() or 0

    return {
        "total_leads": total_leads,
        "messages_sent": messages_sent,
        "open_rate": round(opens / messages_sent, 4),
        "click_rate": round(clicks / messages_sent, 4),
        "reply_rate": round(replies / messages_sent, 4),
        "book_rate": round(booked / total_leads, 4) if total_leads > 0 else 0.0,
    }


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=30)

    # Get daily sends
    sends_result = await session.execute(
        select(
            cast(Message.sent_at, Date).label("day"),
            func.count().label("count"),
        )
        .join(Campaign, Message.campaign_id == Campaign.id)
        .where(
            Campaign.tenant_id == current_user.tenant_id,
            Message.sent_at >= start_date,
            Message.sent_at.isnot(None),
        )
        .group_by("day")
    )
    sends_by_day = {row[0]: row[1] for row in sends_result.all()}

    # Get daily events (opens, clicks, replies)
    events_result = await session.execute(
        select(
            cast(Event.occurred_at, Date).label("day"),
            Event.event_type,
            func.count().label("count"),
        )
        .join(Message, Event.message_id == Message.id)
        .join(Campaign, Message.campaign_id == Campaign.id)
        .where(
            Campaign.tenant_id == current_user.tenant_id,
            Event.occurred_at >= start_date,
        )
        .group_by("day", Event.event_type)
    )

    events_by_day: dict[date, dict[str, int]] = {}
    for row in events_result.all():
        day = row[0]
        event_type = row[1]
        count = row[2]
        if day not in events_by_day:
            events_by_day[day] = {}
        event_key = event_type.value if hasattr(event_type, "value") else str(event_type)
        events_by_day[day][event_key] = count

    # Build timeline data points for last 30 days
    data = []
    for i in range(30):
        day = (start_date + timedelta(days=i + 1)).date()
        day_events = events_by_day.get(day, {})
        data.append(
            TimelineDataPoint(
                date=day,
                sends=sends_by_day.get(day, 0),
                opens=day_events.get("open", 0),
                clicks=day_events.get("click", 0),
                replies=day_events.get("reply", 0),
            )
        )

    return {"data": data}


@router.get("/top-sequences", response_model=TopSequencesResponse)
async def get_top_sequences(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    # Single aggregated query to avoid N+1 per sequence
    result = await session.execute(
        select(
            Sequence.id,
            Sequence.name,
            func.count(Message.id).label("total_messages"),
            func.count(
                case((Event.event_type == EventType.reply, Event.id))
            ).label("reply_count"),
        )
        .join(Campaign, Campaign.sequence_id == Sequence.id)
        .join(Message, Message.campaign_id == Campaign.id)
        .outerjoin(Event, Event.message_id == Message.id)
        .where(Sequence.tenant_id == current_user.tenant_id)
        .group_by(Sequence.id, Sequence.name)
        .having(func.count(Message.id) > 0)
    )

    items = []
    for row in result.all():
        total_messages = row.total_messages
        reply_count = row.reply_count
        items.append(
            TopSequenceItem(
                id=row.id,
                name=row.name,
                reply_rate=round(reply_count / total_messages, 4),
                total_messages=total_messages,
            )
        )

    # Sort by reply rate descending
    items.sort(key=lambda x: x.reply_rate, reverse=True)
    return {"items": items}

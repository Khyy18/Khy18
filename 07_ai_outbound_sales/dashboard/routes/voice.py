"""Voice Dashboard API routes - call management, scripts, and analytics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Call, CallScript, CallStatus, CallOutcome, User
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


# ---------- Request/Response Models ----------


class CallScriptCreate(BaseModel):
    name: str
    script_json: dict = {}
    voice_id: Optional[str] = None
    language: str = "en"


class CallScriptUpdate(BaseModel):
    name: Optional[str] = None
    script_json: Optional[dict] = None
    voice_id: Optional[str] = None
    language: Optional[str] = None


class TestCallRequest(BaseModel):
    phone_number: str
    script_id: Optional[str] = None


# ---------- Call Endpoints ----------


@router.get("/calls")
async def list_calls(
    status_filter: Optional[str] = None,
    outcome: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """List calls with optional filters, paginated."""
    query = select(Call).where(Call.tenant_id == current_user.tenant_id)

    if status_filter:
        try:
            cs = CallStatus(status_filter)
            query = query.where(Call.status == cs)
        except ValueError:
            pass

    if outcome:
        try:
            co = CallOutcome(outcome)
            query = query.where(Call.outcome == co)
        except ValueError:
            pass

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.where(Call.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.where(Call.created_at <= dt_to)
        except ValueError:
            pass

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.order_by(Call.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    calls = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "calls": [
            {
                "id": str(c.id),
                "lead_id": str(c.lead_id),
                "campaign_id": str(c.campaign_id) if c.campaign_id else None,
                "status": c.status.value if c.status else None,
                "outcome": c.outcome.value if c.outcome else None,
                "duration_seconds": c.duration_seconds,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "ended_at": c.ended_at.isoformat() if c.ended_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in calls
        ],
    }


@router.get("/calls/{call_id}")
async def get_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get a single call detail with transcript."""
    result = await session.execute(
        select(Call).where(
            Call.id == call_id,
            Call.tenant_id == current_user.tenant_id,
        )
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    return {
        "id": str(call.id),
        "lead_id": str(call.lead_id),
        "campaign_id": str(call.campaign_id) if call.campaign_id else None,
        "twilio_sid": call.twilio_sid,
        "status": call.status.value if call.status else None,
        "outcome": call.outcome.value if call.outcome else None,
        "duration_seconds": call.duration_seconds,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "recording_url": call.recording_url,
        "transcript": call.transcript,
        "cost_cents": call.cost_cents,
        "script_id": str(call.script_id) if call.script_id else None,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


@router.post("/calls/{call_id}/replay")
async def replay_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get the recording URL for call replay."""
    result = await session.execute(
        select(Call).where(
            Call.id == call_id,
            Call.tenant_id == current_user.tenant_id,
        )
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    if not call.recording_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recording available for this call",
        )

    return {"recording_url": call.recording_url}


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get aggregated voice call statistics."""
    base_query = select(Call).where(Call.tenant_id == current_user.tenant_id)

    # Total calls
    total_result = await session.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total_calls = total_result.scalar() or 0

    # Answered calls
    answered_query = select(Call).where(
        Call.tenant_id == current_user.tenant_id,
        Call.status.in_([CallStatus.answered, CallStatus.in_progress, CallStatus.completed]),
    )
    answered_result = await session.execute(
        select(func.count()).select_from(answered_query.subquery())
    )
    answered_count = answered_result.scalar() or 0

    # Average duration
    avg_result = await session.execute(
        select(func.avg(Call.duration_seconds)).where(
            Call.tenant_id == current_user.tenant_id,
            Call.duration_seconds.isnot(None),
        )
    )
    avg_duration = avg_result.scalar() or 0.0

    # Outcomes breakdown
    outcomes_query = await session.execute(
        select(Call.outcome, func.count()).where(
            Call.tenant_id == current_user.tenant_id,
            Call.outcome.isnot(None),
        ).group_by(Call.outcome)
    )
    outcomes = {row[0].value: row[1] for row in outcomes_query.all() if row[0]}

    # Conversion rate (qualified / total answered)
    qualified_count = outcomes.get("qualified", 0)
    conversion_rate = (
        (qualified_count / answered_count * 100) if answered_count > 0 else 0.0
    )

    return {
        "total_calls": total_calls,
        "answered_count": answered_count,
        "avg_duration_seconds": round(float(avg_duration), 1),
        "outcomes": outcomes,
        "conversion_rate": round(conversion_rate, 2),
    }


# ---------- Script Endpoints ----------


@router.post("/scripts")
async def create_script(
    data: CallScriptCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a new call script."""
    script = CallScript(
        tenant_id=current_user.tenant_id,
        name=data.name,
        script_json=data.script_json,
        voice_id=data.voice_id,
        language=data.language,
    )
    session.add(script)
    await session.commit()
    await session.refresh(script)

    return {
        "id": str(script.id),
        "name": script.name,
        "script_json": script.script_json,
        "voice_id": script.voice_id,
        "language": script.language,
        "created_at": script.created_at.isoformat() if script.created_at else None,
    }


@router.get("/scripts")
async def list_scripts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[dict]:
    """List all call scripts for the tenant."""
    result = await session.execute(
        select(CallScript)
        .where(CallScript.tenant_id == current_user.tenant_id)
        .order_by(CallScript.created_at.desc())
    )
    scripts = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "name": s.name,
            "script_json": s.script_json,
            "voice_id": s.voice_id,
            "language": s.language,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in scripts
    ]


@router.put("/scripts/{script_id}")
async def update_script(
    script_id: str,
    data: CallScriptUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Update an existing call script."""
    result = await session.execute(
        select(CallScript).where(
            CallScript.id == script_id,
            CallScript.tenant_id == current_user.tenant_id,
        )
    )
    script = result.scalar_one_or_none()
    if script is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script not found",
        )

    if data.name is not None:
        script.name = data.name
    if data.script_json is not None:
        script.script_json = data.script_json
    if data.voice_id is not None:
        script.voice_id = data.voice_id
    if data.language is not None:
        script.language = data.language

    await session.commit()
    await session.refresh(script)

    return {
        "id": str(script.id),
        "name": script.name,
        "script_json": script.script_json,
        "voice_id": script.voice_id,
        "language": script.language,
        "created_at": script.created_at.isoformat() if script.created_at else None,
    }


@router.delete("/scripts/{script_id}")
async def delete_script(
    script_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Delete a call script."""
    result = await session.execute(
        select(CallScript).where(
            CallScript.id == script_id,
            CallScript.tenant_id == current_user.tenant_id,
        )
    )
    script = result.scalar_one_or_none()
    if script is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script not found",
        )

    await session.delete(script)
    await session.commit()

    return {"deleted": True, "id": script_id}


# ---------- Test Call Endpoint ----------


@router.post("/test-call")
async def initiate_test_call(
    data: TestCallRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Initiate a test call to a specified phone number."""
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice call service is not available",
        )

    # Look up or create a lead for the test call phone number
    from core.models import Lead, LeadStatus

    result = await session.execute(
        select(Lead).where(
            Lead.tenant_id == current_user.tenant_id,
            Lead.email == f"test-call-{data.phone_number}@internal",
        )
    )
    lead = result.scalar_one_or_none()

    if lead is None:
        import uuid as _uuid

        lead = Lead(
            id=_uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            email=f"test-call-{data.phone_number}@internal",
            first_name="Test",
            last_name="Call",
            status=LeadStatus.new,
            enrichment_data={"phone": data.phone_number},
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)

    # Initiate the call via call_manager
    call_result = await call_manager.start_call(
        lead_id=lead.id,
        tenant_id=current_user.tenant_id,
        script_id=data.script_id if data.script_id else None,
    )

    return {
        "status": "initiated",
        "call_id": call_result.get("call_id"),
        "twilio_sid": call_result.get("twilio_sid"),
        "phone_number": data.phone_number,
        "script_id": data.script_id,
    }

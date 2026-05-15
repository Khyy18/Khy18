from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Sequence, User
from dashboard.auth import get_current_user
from dashboard.schemas import (
    SequenceCreate,
    SequenceListResponse,
    SequenceResponse,
    SequenceUpdate,
)

router = APIRouter(prefix="/api/sequences", tags=["sequences"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.post("/", response_model=SequenceResponse, status_code=status.HTTP_201_CREATED)
async def create_sequence(
    data: SequenceCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Sequence:
    sequence = Sequence(
        tenant_id=current_user.tenant_id,
        name=data.name,
        steps=data.steps,
    )
    session.add(sequence)
    await session.flush()
    await session.refresh(sequence)
    return sequence


@router.get("/", response_model=SequenceListResponse)
async def list_sequences(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    count_query = select(func.count()).select_from(Sequence).where(
        Sequence.tenant_id == current_user.tenant_id
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(
        select(Sequence)
        .where(Sequence.tenant_id == current_user.tenant_id)
        .limit(limit)
        .offset(offset)
    )
    items = list(result.scalars().all())

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{sequence_id}", response_model=SequenceResponse)
async def get_sequence(
    sequence_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Sequence:
    result = await session.execute(
        select(Sequence).where(
            Sequence.id == sequence_id,
            Sequence.tenant_id == current_user.tenant_id,
        )
    )
    sequence = result.scalar_one_or_none()
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found")
    return sequence


@router.put("/{sequence_id}", response_model=SequenceResponse)
async def update_sequence(
    sequence_id: UUID,
    data: SequenceUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Sequence:
    result = await session.execute(
        select(Sequence).where(
            Sequence.id == sequence_id,
            Sequence.tenant_id == current_user.tenant_id,
        )
    )
    sequence = result.scalar_one_or_none()
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sequence, field, value)

    await session.flush()
    await session.refresh(sequence)
    return sequence

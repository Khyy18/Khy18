import csv
import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import Lead, User
from dashboard.auth import get_current_user
from dashboard.schemas import (
    LeadCreate,
    LeadImportResponse,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)

router = APIRouter(prefix="/api/leads", tags=["leads"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: LeadCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Lead:
    lead = Lead(
        tenant_id=current_user.tenant_id,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        company=data.company,
        title=data.title,
        linkedin_url=data.linkedin_url,
    )
    session.add(lead)
    await session.flush()
    await session.refresh(lead)
    return lead


@router.get("/", response_model=LeadListResponse)
async def list_leads(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    campaign_id: Optional[UUID] = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    base_query = select(Lead).where(Lead.tenant_id == current_user.tenant_id)
    count_query = select(func.count()).select_from(Lead).where(
        Lead.tenant_id == current_user.tenant_id
    )

    if status_filter:
        base_query = base_query.where(Lead.status == status_filter)
        count_query = count_query.where(Lead.status == status_filter)

    if campaign_id:
        from core.models import Message

        lead_ids_subq = (
            select(Message.lead_id)
            .where(Message.campaign_id == campaign_id)
            .distinct()
            .subquery()
        )
        base_query = base_query.where(Lead.id.in_(select(lead_ids_subq)))
        count_query = count_query.where(Lead.id.in_(select(lead_ids_subq)))

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(
        base_query.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
    )
    items = list(result.scalars().all())

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Lead:
    result = await session.execute(
        select(Lead)
        .options(selectinload(Lead.messages))
        .where(
            Lead.id == lead_id,
            Lead.tenant_id == current_user.tenant_id,
        )
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: UUID,
    data: LeadUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Lead:
    result = await session.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.tenant_id == current_user.tenant_id,
        )
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead, field, value)

    await session.flush()
    await session.refresh(lead)
    return lead


MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/import", response_model=LeadImportResponse)
async def import_leads(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    # Check file size (read and enforce 10 MB limit)
    content = await file.read()
    if len(content) > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum allowed size is 10 MB.",
        )

    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    count = 0
    for row in reader:
        # Skip rows with empty or missing email
        email = (row.get("email") or "").strip()
        if not email:
            continue

        lead = Lead(
            tenant_id=current_user.tenant_id,
            email=email,
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            company=row.get("company", ""),
            title=row.get("title", ""),
            linkedin_url=row.get("linkedin_url") or None,
        )
        session.add(lead)
        count += 1

    await session.flush()
    return {"imported_count": count}
